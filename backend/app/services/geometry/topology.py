import networkx as nx


def build_room_graph(rooms: list[dict], adjacencies: list[tuple[str, str]]) -> nx.DiGraph:
    """
    Builds a Directed Acyclic Graph (DAG) representing the room access flow.
    
    Each room dict should contain at least:
        - 'name': Unique identifier
        - 'type': 'Bedroom', 'Kitchen', 'Living Room', 'Bathroom', 'Corridor', etc.
        - 'requires_ventilation': bool
        - 'adjacent_to_road': bool (True if room can share a window with the road/exterior)
    """
    G = nx.DiGraph()
    for room in rooms:
        name = room['name']
        G.add_node(name, **room)
        
    for u, v in adjacencies:
        if u in G and v in G:
            G.add_edge(u, v)
            
    return G

def validate_privacy(G: nx.DiGraph, main_door: str = "Main Door") -> tuple[bool, str]:
    """
    Validates that the room layout graph does not violate privacy.
    The path from the Main Door to any public room (Kitchen, Living Room, Dining Room)
    should not pass through a private room (Bedroom, Bathroom).
    """
    # Convert DiGraph to Undirected for access/walkability checking, since movement is bidirectional.
    U = G.to_undirected()
    
    private_types = {'Bedroom', 'Bathroom'}
    public_types = {'Kitchen', 'Living Room', 'Dining Room', 'Balcony', 'Staircase'}
    
    # Identify target public rooms in the graph
    targets = [n for n, d in U.nodes(data=True) if d.get('type') in public_types or n in public_types]
    
    # If no public rooms are on this floor, privacy validation passes vacuously
    if not targets:
        return True, "Privacy validation passed (no public rooms on this floor)."
        
    if main_door not in U:
        # If Main Door is not in the graph, we find the node of type 'Main Door' or 'Entrance'
        entrances = [n for n, d in U.nodes(data=True) if d.get('type') in ['Entrance', 'Main Door']]
        if entrances:
            main_door = entrances[0]
        else:
            # Fallback to Staircase node for upper floors
            staircases = [n for n, d in U.nodes(data=True) if d.get('type') == 'Staircase' or 'stair' in n.lower()]
            if staircases:
                main_door = staircases[0]
            else:
                return False, "Main Door / Entrance / Staircase node not found in the graph."
            
    # Identify all private nodes in the graph
    private_nodes = [
        n for n, d in U.nodes(data=True) 
        if d.get('type') in private_types or 'bedroom' in n.lower() or 'bathroom' in n.lower()
    ]
    
    for target in targets:
        if target == main_door:
            continue
            
        # Create a copy of the access graph and remove private rooms
        U_clean = U.copy()
        nodes_to_remove = [node for node in private_nodes if node != main_door and node != target]
        U_clean.remove_nodes_from(nodes_to_remove)
        
        # Verify if a privacy-compliant path exists
        if not nx.has_path(U_clean, source=main_door, target=target):
            # If a path existed originally, it means all possible paths must go through a private room
            if nx.has_path(U, source=main_door, target=target):
                return False, f"Privacy violation: All access routes from {main_door} to {target} force walking through a private room."
            else:
                return False, f"Unreachable room: No access route from {main_door} to {target}."
            
    return True, "Privacy validation passed."

def calculate_ventilation_and_ots(G: nx.DiGraph, setbacks: dict | None = None) -> tuple[nx.DiGraph, list[dict]]:
    """
    Calculates the ventilation distance to the exterior (Air Node).
    If a room requiring ventilation has a distance > 1, it triggers procedural OTS shaft generation.
    
    Returns:
        A tuple of (Modified Graph with OTS nodes, List of procedurally generated OTS shaft configurations).
    """
    # Create a ventilation graph. The root is the "AirNode".
    # All nodes in the original graph that are adjacent to the road/exterior are connected to "AirNode".
    vent_G = nx.Graph()
    vent_G.add_node("AirNode", type="Air", name="AirNode")
    
    # Add room nodes to the ventilation graph
    for name, data in G.nodes(data=True):
        vent_G.add_node(name, **data)
        if data.get('adjacent_to_road', False):
            vent_G.add_edge("AirNode", name)

            
    # Calculate shortest path lengths from AirNode to all nodes
    distances = {}
    try:
        lengths = nx.single_source_shortest_path_length(vent_G, "AirNode")
        for node in G.nodes:
            distances[node] = lengths.get(node, float('inf'))
    except Exception:  # noqa: BLE001
        for node in G.nodes:
            distances[node] = float('inf')
            
    new_G = G.copy()
    ots_shafts = []
    
    # Iterate through rooms requiring ventilation. If distance > 1, generate OTS shaft.
    for node, data in G.nodes(data=True):
        if data.get('requires_ventilation', False):
            dist = distances.get(node, float('inf'))
            if dist > 1:
                # Procedurally generate an OTS Shaft for this room
                ots_name = f"OTS_{node}"
                ots_config = {
                    'name': ots_name,
                    'type': 'OTS',
                    'ventilates': node,
                    'min_area': 9.0,   # Minimum 3x3 ft = 9 sq ft (standard OTS)
                    'min_width': 3.0,   # Minimum 3 ft width
                    'min_height': 3.0,  # Minimum 3 ft height
                    'requires_ventilation': False,
                    'adjacent_to_road': False
                }
                ots_shafts.append(ots_config)
                
                # Add OTS node to the room graph
                new_G.add_node(ots_name, **ots_config)
                # An OTS shaft shares a ventilation connection with the room and the air
                new_G.add_edge(ots_name, node)
                
    return new_G, ots_shafts
