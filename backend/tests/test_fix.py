"""测试复合句修复"""
from app.services.llm_extraction_service import extract_ir

TEST_USER_ID = "9a9e9803-94d6-4ecd-8d09-66fb4745ef85"

msg = "我认识的人谁住在海边 而且我讨厌吃蛋糕"
print(f"测试: {msg}")
result = extract_ir(text=msg, user_id=TEST_USER_ID, context_entities=[])
if result.success:
    print(f"实体: {[e['name'] for e in result.entities]}")
    print(f"关系: {[(r['source'], r['type'], r['target']) for r in result.relations]}")
else:
    print(f"失败: {result.error}")
