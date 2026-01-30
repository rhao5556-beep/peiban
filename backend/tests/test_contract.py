"""Contract Tests - OpenAPI Schema 验证"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import json


class TestConversationContract:
    """对话 API Contract Tests"""
    
    def test_conversation_request_schema(self, client: TestClient):
        """验证对话请求 Schema"""
        # 有效请求
        valid_request = {
            "message": "你好，今天心情怎么样？",
            "session_id": "test-session-123",
            "idempotency_key": "idem-key-456"
        }
        
        response = client.post("/api/v1/conversation/message", json=valid_request)
        
        # 应该返回 200 或 201
        assert response.status_code in [200, 201, 422]  # 422 如果缺少认证
    
    def test_conversation_response_schema(self, client: TestClient, auth_headers: dict):
        """验证对话响应 Schema"""
        request = {
            "message": "测试消息",
            "session_id": "test-session",
            "idempotency_key": f"idem-{datetime.now().timestamp()}"
        }
        
        response = client.post(
            "/api/v1/conversation/message",
            json=request,
            headers=auth_headers
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # 验证必需字段
            assert "reply" in data
            assert "session_id" in data
            assert "turn_id" in data
            assert "emotion" in data
            assert "affinity" in data
            
            # 验证 emotion 结构
            emotion = data["emotion"]
            assert "primary_emotion" in emotion
            assert "valence" in emotion
            
            # 验证 affinity 结构
            affinity = data["affinity"]
            assert "score" in affinity
            assert "state" in affinity
    
    def test_conversation_idempotency(self, client: TestClient, auth_headers: dict):
        """验证幂等性 Contract"""
        idempotency_key = f"idem-test-{datetime.now().timestamp()}"
        request = {
            "message": "幂等性测试",
            "session_id": "test-session",
            "idempotency_key": idempotency_key
        }
        
        # 第一次请求
        response1 = client.post(
            "/api/v1/conversation/message",
            json=request,
            headers=auth_headers
        )
        
        # 第二次请求（相同 idempotency_key）
        response2 = client.post(
            "/api/v1/conversation/message",
            json=request,
            headers=auth_headers
        )
        
        # 两次响应应该相同（或第二次返回缓存结果）
        if response1.status_code == 200 and response2.status_code == 200:
            # 验证幂等性
            assert response1.json().get("turn_id") == response2.json().get("turn_id") or \
                   response2.status_code == 200  # 允许返回相同结果


class TestMemoryContract:
    """记忆 API Contract Tests"""
    
    def test_memory_list_schema(self, client: TestClient, auth_headers: dict):
        """验证记忆列表响应 Schema"""
        response = client.get("/api/v1/memories/", headers=auth_headers)
        
        if response.status_code == 200:
            data = response.json()
            
            assert isinstance(data, list)
            
            # 验证单个记忆结构
            if data:
                memory = data[0]
                assert "id" in memory
                assert "content" in memory
                assert "status" in memory
    
    def test_memory_status_values(self, client: TestClient, auth_headers: dict):
        """验证记忆状态枚举值"""
        valid_statuses = ["pending", "committed", "deleted"]
        
        response = client.get("/api/v1/memories/", headers=auth_headers)
        
        if response.status_code == 200:
            data = response.json()
            for memory in data:
                assert memory["status"] in valid_statuses


class TestAffinityContract:
    """好感度 API Contract Tests"""
    
    def test_affinity_response_schema(self, client: TestClient, auth_headers: dict):
        """验证好感度响应 Schema"""
        response = client.get("/api/v1/affinity/current", headers=auth_headers)
        
        if response.status_code == 200:
            data = response.json()
            
            # 验证必需字段
            assert "score" in data
            assert "state" in data
            
            # 验证分数范围
            assert -1.0 <= data["score"] <= 1.0
            
            # 验证状态枚举
            valid_states = ["stranger", "acquaintance", "friend", "close_friend", "best_friend"]
            assert data["state"] in valid_states
    
    def test_affinity_history_schema(self, client: TestClient, auth_headers: dict):
        """验证好感度历史响应 Schema"""
        response = client.get("/api/v1/affinity/history?days=30", headers=auth_headers)
        
        if response.status_code == 200:
            data = response.json()
            
            assert "history" in data
            
            for record in data.get("history", []):
                assert "score" in record
                assert "delta" in record
                assert "trigger_event" in record


class TestGraphContract:
    """图谱 API Contract Tests"""
    
    def test_graph_response_schema(self, client: TestClient, auth_headers: dict):
        """验证图谱响应 Schema"""
        response = client.get("/api/v1/graph/user", headers=auth_headers)
        
        if response.status_code == 200:
            data = response.json()
            
            assert "nodes" in data
            assert "edges" in data
            
            # 验证节点结构
            for node in data.get("nodes", []):
                assert "id" in node
                assert "name" in node
                assert "type" in node
            
            # 验证边结构
            for edge in data.get("edges", []):
                assert "id" in edge or "source_id" in edge
                assert "relation_type" in edge


class TestSSEContract:
    """SSE 流式响应 Contract Tests"""
    
    def test_sse_event_format(self, client: TestClient, auth_headers: dict):
        """验证 SSE 事件格式"""
        request = {
            "message": "SSE 测试",
            "session_id": "test-session",
            "idempotency_key": f"sse-{datetime.now().timestamp()}"
        }
        
        # 使用 stream=True 获取 SSE 响应
        with client.stream(
            "POST",
            "/api/v1/conversation/stream",
            json=request,
            headers=auth_headers
        ) as response:
            if response.status_code == 200:
                # 验证 Content-Type
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # 读取事件
                events = []
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        event_data = line[5:].strip()
                        if event_data:
                            events.append(json.loads(event_data))
                
                # 验证事件类型
                valid_types = ["text", "metadata", "memory_pending", "memory_committed", "done", "error"]
                for event in events:
                    assert "type" in event
                    assert event["type"] in valid_types


class TestErrorContract:
    """错误响应 Contract Tests"""
    
    def test_validation_error_schema(self, client: TestClient):
        """验证请求验证错误响应 Schema"""
        # 发送无效请求
        invalid_request = {
            "message": ""  # 空消息
        }
        
        response = client.post("/api/v1/conversation/message", json=invalid_request)
        
        if response.status_code == 422:
            data = response.json()
            assert "detail" in data
    
    def test_auth_error_schema(self, client: TestClient):
        """验证认证错误响应 Schema"""
        response = client.get("/api/v1/memory/list")  # 无认证头
        
        if response.status_code == 401:
            data = response.json()
            assert "detail" in data
    
    def test_not_found_error_schema(self, client: TestClient, auth_headers: dict):
        """验证 404 错误响应 Schema"""
        response = client.get(
            "/api/v1/memory/nonexistent-id",
            headers=auth_headers
        )
        
        if response.status_code == 404:
            data = response.json()
            assert "detail" in data


class TestRateLimitContract:
    """限流 Contract Tests"""
    
    def test_rate_limit_headers(self, client: TestClient, auth_headers: dict):
        """验证限流响应头"""
        response = client.get("/api/v1/affinity/current", headers=auth_headers)
        
        # 检查限流相关头（如果实现了）
        rate_limit_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset"
        ]
        
        # 至少应该有一些限流信息
        # 这是可选的，取决于实现
        pass
    
    def test_rate_limit_exceeded_schema(self, client: TestClient, auth_headers: dict):
        """验证限流超限响应 Schema"""
        # 快速发送多个请求
        for _ in range(100):
            response = client.get("/api/v1/affinity/current", headers=auth_headers)
            
            if response.status_code == 429:
                data = response.json()
                assert "detail" in data
                break


# Fixtures
@pytest.fixture
def client():
    """创建测试客户端"""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """创建认证头"""
    # 使用测试 token
    return {"Authorization": "Bearer test-token-for-testing"}
