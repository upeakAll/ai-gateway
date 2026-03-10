# 弹性策略

## 概述

弹性策略模块提供重试、熔断、降级等机制，保证系统在异常情况下的稳定性。

---

## 架构

```
请求 ──→ 重试策略 ──→ 熔断器 ──→ 适配器调用 ──→ 响应
            │            │            │
            │            │            ↓
            │            │       健康检查
            │            │
            ↓            ↓
        失败重试     熔断保护
            │            │
            ↓            ↓
        降级处理 ←────────┘
```

---

## 重试策略

### 配置

```python
@dataclass
class RetryConfig:
    max_retries: int = 3           # 最大重试次数
    base_delay: float = 1.0        # 基础延迟(秒)
    max_delay: float = 60.0        # 最大延迟(秒)
    exponential_base: float = 2.0  # 指数基数
    jitter: bool = True            # 是否添加抖动
    retryable_errors: List[str] = None  # 可重试的错误类型
```

### 指数退避 + 抖动

```python
def calculate_delay(self, attempt: int) -> float:
    """计算重试延迟"""
    delay = self.base_delay * (self.exponential_base ** attempt)
    delay = min(delay, self.max_delay)

    if self.jitter:
        # 添加随机抖动 (0.5 ~ 1.5倍)
        delay *= (0.5 + random.random())

    return delay
```

### 重试执行器

```python
class RetryExecutor:
    """重试执行器"""

    def __init__(self, config: RetryConfig):
        self.config = config

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e

                if not self._should_retry(e, attempt):
                    raise

                delay = self.calculate_delay(attempt)
                logger.warning(
                    f"Retry {attempt + 1}/{self.config.max_retries} "
                    f"after {delay:.2f}s: {e}"
                )
                await asyncio.sleep(delay)

        raise last_error

    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.config.max_retries:
            return False

        # 网络错误重试
        if isinstance(error, (httpx.NetworkError, httpx.TimeoutException)):
            return True

        # 5xx 服务器错误重试
        if isinstance(error, httpx.HTTPStatusError):
            if error.response.status_code >= 500:
                return True
            if error.response.status_code == 429:  # Rate limit
                return True

        return False
```

### 使用示例

```python
retry_executor = RetryExecutor(RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0
))

response = await retry_executor.execute(
    adapter.chat,
    request
)
```

---

## 熔断器

### 状态机

```
         失败率 > 阈值
    ┌──────────────────────┐
    │                      │
    ▼                      │
┌────────┐  成功率 > 阈值  ┌────────┐
│ CLOSED │ ──────────────→│  OPEN  │
└────────┘                └────────┘
    ▲                          │
    │                          │ 超时后
    │    成功请求              │
    │                          ▼
    │                    ┌──────────┐
    └────────────────────│ HALF_OPEN│
                         └──────────┘
```

### 配置

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5      # 触发熔断的失败次数
    success_threshold: int = 3      # 恢复所需的成功次数
    timeout: float = 60.0           # OPEN状态超时时间(秒)
    half_open_requests: int = 1     # HALF_OPEN状态允许的请求数
```

### 熔断器实现

```python
class CircuitBreaker:
    """熔断器"""

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = self.STATE_CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        async with self._lock:
            await self._check_state_transition()

            if self.state == self.STATE_OPEN:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is open"
                )

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _check_state_transition(self):
        """检查状态转换"""
        if self.state == self.STATE_OPEN:
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.config.timeout:
                self.state = self.STATE_HALF_OPEN
                self.success_count = 0

    async def _on_success(self):
        """成功回调"""
        async with self._lock:
            self.failure_count = 0

            if self.state == self.STATE_HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = self.STATE_CLOSED

    async def _on_failure(self):
        """失败回调"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == self.STATE_HALF_OPEN:
                self.state = self.STATE_OPEN
            elif self.failure_count >= self.config.failure_threshold:
                self.state = self.STATE_OPEN

    async def reset(self):
        """重置熔断器"""
        async with self._lock:
            self.state = self.STATE_CLOSED
            self.failure_count = 0
            self.success_count = 0
```

### 使用示例

```python
circuit_breaker = CircuitBreaker(
    "channel-openai",
    CircuitBreakerConfig(
        failure_threshold=5,
        timeout=60.0
    )
)

try:
    response = await circuit_breaker.call(adapter.chat, request)
except CircuitBreakerOpenError:
    # 熔断器打开，使用降级策略
    response = await fallback_handler(request)
```

---

## 降级策略

### 降级类型

```python
class FallbackStrategy(Enum):
    MODEL_DOWNGRADE = "model_downgrade"      # 模型降级
    CHANNEL_FAILOVER = "channel_failover"    # 渠道切换
    DEFAULT_RESPONSE = "default_response"    # 默认响应
    CACHE_RESPONSE = "cache_response"        # 缓存响应
```

### 降级处理器

```python
class FallbackHandler:
    """降级处理器"""

    def __init__(
        self,
        model_downgrades: Dict[str, str],
        channel_selector: ChannelSelector
    ):
        self.model_downgrades = model_downgrades
        self.channel_selector = channel_selector

    async def handle(
        self,
        request: ChatRequest,
        error: Exception,
        channel: Channel
    ) -> ChatResponse:
        """处理降级"""

        # 1. 尝试模型降级
        if request.model in self.model_downgrades:
            downgrade_model = self.model_downgrades[request.model]
            logger.info(f"Downgrading model: {request.model} -> {downgrade_model}")

            try:
                request.model = downgrade_model
                return await self._try_other_channel(request, channel)
            except Exception:
                pass

        # 2. 尝试渠道切换
        try:
            return await self._try_other_channel(request, channel)
        except Exception:
            pass

        # 3. 返回默认响应
        return self._default_response(request, error)

    async def _try_other_channel(
        self,
        request: ChatRequest,
        failed_channel: Channel
    ) -> ChatResponse:
        """尝试其他渠道"""
        other_channels = await self.channel_selector.get_available_channels(
            request.model,
            exclude=[failed_channel.id]
        )

        for channel in other_channels:
            try:
                adapter = AdapterRegistry.create(channel)
                return await adapter.chat(request)
            except Exception:
                continue

        raise NoAvailableChannelError("No available channels")

    def _default_response(
        self,
        request: ChatRequest,
        error: Exception
    ) -> ChatResponse:
        """返回默认响应"""
        return ChatResponse(
            id=f"fallback-{uuid.uuid4()}",
            model=request.model,
            choices=[Choice(
                index=0,
                message=Message(
                    role="assistant",
                    content="抱歉，服务暂时不可用，请稍后重试。"
                ),
                finish_reason="error"
            )],
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            created=int(time.time())
        )
```

### 降级配置

```yaml
fallback:
  model_downgrades:
    "gpt-4o": "gpt-4o-mini"
    "claude-3-opus": "claude-3-sonnet"
    "claude-3-sonnet": "claude-3-haiku"

  default_response: |
    抱歉，服务暂时不可用，请稍后重试。

  enable_cache_fallback: true
  cache_ttl: 3600
```

---

## 健康检查

### 主动健康检查

```python
class ActiveHealthChecker:
    """主动健康检查"""

    def __init__(self, interval: int = 60):
        self.interval = interval
        self._running = False

    async def start(self):
        """启动健康检查"""
        self._running = True
        while self._running:
            await self._check_all_channels()
            await asyncio.sleep(self.interval)

    async def _check_all_channels(self):
        """检查所有渠道"""
        channels = await self.get_active_channels()

        for channel in channels:
            try:
                result = await self._check_channel(channel)
                channel.health_status = result.status
                channel.avg_response_time = result.latency_ms
            except Exception as e:
                channel.health_status = "unhealthy"
                logger.error(f"Health check failed for {channel.name}: {e}")

    async def _check_channel(self, channel: Channel) -> HealthCheckResult:
        """检查单个渠道"""
        adapter = AdapterRegistry.create(channel)

        # 发送测试请求
        test_request = ChatRequest(
            model="test",
            messages=[Message(role="user", content="ping")],
            max_tokens=5
        )

        start_time = time.time()
        await adapter.chat(test_request)
        latency_ms = int((time.time() - start_time) * 1000)

        return HealthCheckResult(status="healthy", latency_ms=latency_ms)
```

### 被动健康检查

```python
class PassiveHealthChecker:
    """被动健康检查 - 基于实际请求统计"""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.stats: Dict[str, deque] = {}

    def record_request(
        self,
        channel_id: str,
        success: bool,
        latency_ms: int
    ):
        """记录请求结果"""
        if channel_id not in self.stats:
            self.stats[channel_id] = deque(maxlen=self.window_size)

        self.stats[channel_id].append({
            "success": success,
            "latency_ms": latency_ms,
            "timestamp": time.time()
        })

    def get_health_status(self, channel_id: str) -> str:
        """获取健康状态"""
        if channel_id not in self.stats:
            return "healthy"

        records = list(self.stats[channel_id])
        if not records:
            return "healthy"

        # 计算成功率
        success_rate = sum(1 for r in records if r["success"]) / len(records)

        # 计算平均延迟
        avg_latency = sum(r["latency_ms"] for r in records) / len(records)

        # 判断健康状态
        if success_rate >= 0.99 and avg_latency < 1000:
            return "healthy"
        elif success_rate >= 0.95 and avg_latency < 3000:
            return "degraded"
        else:
            return "unhealthy"
```

### 混合健康检查

```python
class HybridHealthChecker:
    """混合健康检查 - 结合主动和被动"""

    def __init__(self):
        self.active_checker = ActiveHealthChecker(interval=60)
        self.passive_checker = PassiveHealthChecker(window_size=100)

    def get_health_status(self, channel_id: str) -> str:
        """获取综合健康状态"""
        active_status = self.active_checker.get_status(channel_id)
        passive_status = self.passive_checker.get_health_status(channel_id)

        # 取较差的状态
        status_priority = {"healthy": 0, "degraded": 1, "unhealthy": 2}
        if status_priority[active_status] > status_priority[passive_status]:
            return active_status
        return passive_status
```

---

## 组合使用

```python
class ResilientChannelClient:
    """弹性渠道客户端"""

    def __init__(self, channel: Channel):
        self.channel = channel
        self.retry_executor = RetryExecutor(RetryConfig())
        self.circuit_breaker = CircuitBreaker(
            f"channel-{channel.id}",
            CircuitBreakerConfig()
        )
        self.fallback_handler = FallbackHandler(...)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        try:
            # 熔断器包装
            return await self.circuit_breaker.call(
                # 重试包装
                self.retry_executor.execute,
                self._do_chat,
                request
            )
        except CircuitBreakerOpenError as e:
            # 降级处理
            return await self.fallback_handler.handle(
                request, e, self.channel
            )

    async def _do_chat(self, request: ChatRequest) -> ChatResponse:
        adapter = AdapterRegistry.create(self.channel)
        return await adapter.chat(request)
```

---

*最后更新: 2026-03-10*
