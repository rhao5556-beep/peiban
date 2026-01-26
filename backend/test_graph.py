import asyncio
from app.services.graph_service import GraphService
from app.core.database import get_neo4j_driver

async def test_graph():
    driver = get_neo4j_driver()
    if not driver:
        print('Neo4j driver not initialized')
        return
    
    service = GraphService(driver)
    user_id = 'test_user_123'
    
    try:
        graph = await service.get_user_graph(user_id)
        print(f'Nodes: {len(graph.get("nodes", []))}')
        print(f'Edges: {len(graph.get("edges", []))}')
        if graph.get('nodes'):
            print('First node:', graph['nodes'][0])
        if graph.get('edges'):
            print('First edge:', graph['edges'][0])
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    asyncio.run(test_graph())