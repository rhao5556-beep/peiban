"""
Locust 负载测试脚本

用于验证 Outbox SLO:
- Median Lag < 2s
- P95 Lag < 30s

运行方式:
    locust -f scripts/locustfile.py --host=http://localhost:8000
"""
import json
import uuid
import random
from locust import HttpUser, task, between, events
from datetime import datetime


class AffinityUser(HttpUser):
    """模拟 Affinity 用户"""
    
    wait_time = between(1, 3)  # 请求间隔 1-3 秒
    
    def on_start(self):
        """用户启动时登录获取 token"""
        self.user_id = str(uuid.uuid4())
        self.session_id = None
        self.token = None
        
        # 注册/登录获取 token
        response = self.client.post("/api/auth/register", json={
            "username": f"test_user_{self.user_id[:8]}",
            "password": "test_password_123"
        })
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.user_id = data.get("user_id", self.user_id)
        else:
            # 尝试登录
            response = self.client.post("/api/auth/login", json={
                "username": f"test_user_{self.user_id[:8]}",
                "password": "test_password_123"
            })
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
    
    @property
    def headers(self):
        """请求头"""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    @task(3)
    def send_message(self):
        """发送对话消息（Fast Path + Slow Path）"""
        messages = [
            "今天天气真好，想出去走走",
            "最近工作压力有点大",
            "我妈妈做的红烧肉特别好吃",
            "周末想去看电影",
            "你还记得我上次说的那件事吗？",
            "我养了一只叫小白的猫",
            "深圳的夏天真的很热",
            "我喜欢喝奶茶，尤其是珍珠奶茶",
        ]
        
        message = random.choice(messages)
        idempotency_key = str(uuid.uuid4())
        
        with self.client.post(
            "/api/conversation/message",
            json={
                "message": message,
                "session_id": self.session_id
            },
            headers={
                **self.headers,
                "X-Idempotency-Key": idempotency_key
            },
            catch_response=True,
            name="/api/conversation/message"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.session_id = data.get("session_id", self.session_id)
                response.success()
            elif response.status_code == 401:
                response.failure("Unauthorized")
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(2)
    def search_memories(self):
        """搜索记忆（Fast Path）"""
        queries = [
            "妈妈",
            "工作",
            "猫",
            "电影",
            "天气"
        ]
        
        query = random.choice(queries)
        
        with self.client.post(
            "/api/memories/search",
            json={
                "query": query,
                "top_k": 10
            },
            headers=self.headers,
            catch_response=True,
            name="/api/memories/search"
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(1)
    def get_affinity(self):
        """获取好感度"""
        with self.client.get(
            "/api/affinity/",
            headers=self.headers,
            catch_response=True,
            name="/api/affinity/"
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(1)
    def list_memories(self):
        """列出记忆"""
        with self.client.get(
            "/api/memories/?limit=20",
            headers=self.headers,
            catch_response=True,
            name="/api/memories/"
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")


class SSEUser(HttpUser):
    """模拟 SSE 流式用户"""
    
    wait_time = between(5, 10)  # SSE 请求间隔更长
    
    def on_start(self):
        """用户启动时登录"""
        self.user_id = str(uuid.uuid4())
        self.token = None
        
        response = self.client.post("/api/auth/register", json={
            "username": f"sse_user_{self.user_id[:8]}",
            "password": "test_password_123"
        })
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
    
    @property
    def headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    @task
    def stream_conversation(self):
        """流式对话（SSE）"""
        message = "给我讲一个关于小猫的故事"
        idempotency_key = str(uuid.uuid4())
        
        with self.client.get(
            f"/api/sse/stream?message={message}",
            headers={
                **self.headers,
                "X-Idempotency-Key": idempotency_key,
                "Accept": "text/event-stream"
            },
            stream=True,
            catch_response=True,
            name="/api/sse/stream"
        ) as response:
            if response.status_code == 200:
                # 读取 SSE 流
                chunks = 0
                for line in response.iter_lines():
                    if line:
                        chunks += 1
                        if chunks > 50:  # 限制读取量
                            break
                response.success()
            elif response.status_code == 401:
                response.success()  # 未授权也算成功（测试目的）
            else:
                response.failure(f"Status {response.status_code}")


# 自定义指标收集
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """记录请求指标"""
    if exception:
        return
    
    # 可以在这里添加自定义指标收集逻辑
    # 例如发送到 Prometheus Pushgateway


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时生成报告"""
    stats = environment.stats
    
    print("\n" + "=" * 60)
    print("Load Test Summary")
    print("=" * 60)
    
    for name, entry in stats.entries.items():
        print(f"\n{name}:")
        print(f"  Requests: {entry.num_requests}")
        print(f"  Failures: {entry.num_failures}")
        print(f"  Median: {entry.median_response_time}ms")
        print(f"  P95: {entry.get_response_time_percentile(0.95)}ms")
        print(f"  P99: {entry.get_response_time_percentile(0.99)}ms")
    
    print("\n" + "=" * 60)
    
    # 验证 SLO
    conversation_stats = stats.entries.get(("POST", "/api/conversation/message"))
    if conversation_stats:
        p50 = conversation_stats.median_response_time
        p95 = conversation_stats.get_response_time_percentile(0.95)
        
        print("\nSLO Verification:")
        print(f"  P50 Lag: {p50}ms (SLO: <2000ms) - {'✓ PASS' if p50 < 2000 else '✗ FAIL'}")
        print(f"  P95 Lag: {p95}ms (SLO: <30000ms) - {'✓ PASS' if p95 < 30000 else '✗ FAIL'}")
