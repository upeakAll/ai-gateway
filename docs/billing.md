# 计费系统

## 概述

计费系统提供 Token 级别的精确计费，支持预付费和后付费两种模式。

---

## 计费模式

### 预付费 (Prepaid)

- 提前充值配额
- 请求前检查余额
- 余额不足时拒绝请求
- 适合用量可控的场景

### 后付费 (Postpaid)

- 按实际使用计费
- 月底统一结算
- 无实时余额检查
- 适合企业客户

---

## 价格配置

### 模型定价表

```sql
-- model_configs 表
model_name      | input_price_per_1k | output_price_per_1k
----------------|-------------------|--------------------
gpt-4o          | 0.005             | 0.015
gpt-4o-mini     | 0.00015           | 0.0006
gpt-3.5-turbo   | 0.0005            | 0.0015
claude-3-opus   | 0.015             | 0.075
claude-3-sonnet | 0.003             | 0.015
claude-3-haiku  | 0.00025           | 0.00125
```

### 价格计算公式

```python
cost = (prompt_tokens * input_price_per_1k / 1000 +
        completion_tokens * output_price_per_1k / 1000)
```

---

## 配额管理

### 配额检查

```python
class QuotaManager:
    """配额管理器"""

    async def check_quota(
        self,
        tenant_id: str,
        estimated_cost: Decimal
    ) -> bool:
        """检查配额是否足够"""
        quota = await self.get_quota(tenant_id)

        if quota.billing_mode == BillingMode.POSTPAID:
            return True  # 后付费不检查

        remaining = quota.total - quota.used
        return remaining >= estimated_cost

    async def consume(
        self,
        tenant_id: str,
        cost: Decimal
    ) -> bool:
        """消费配额"""
        quota = await self.get_quota(tenant_id)

        if quota.billing_mode == BillingMode.POSTPAID:
            quota.used += cost
            await self.save_quota(quota)
            return True

        remaining = quota.total - quota.used
        if remaining < cost:
            return False

        quota.used += cost
        await self.save_quota(quota)
        return True

    async def add_quota(
        self,
        tenant_id: str,
        amount: Decimal
    ) -> Decimal:
        """充值配额"""
        quota = await self.get_quota(tenant_id)
        quota.total += amount
        await self.save_quota(quota)
        return quota.total - quota.used
```

### 多级配额检查

```
请求 → 租户配额检查 → Key配额检查 → 子Key配额检查 → 处理
```

```python
async def check_all_quotas(request: ChatRequest, context: RequestContext):
    """多级配额检查"""

    # 1. 租户配额
    tenant_quota = await quota_manager.get_quota(context.tenant_id)
    if not await quota_manager.check_quota(context.tenant_id, estimated_cost):
        raise QuotaExceededError("Tenant quota exceeded")

    # 2. Key配额
    if context.api_key.quota_total > 0:
        key_remaining = context.api_key.quota_total - context.api_key.quota_used
        if key_remaining < estimated_cost:
            raise QuotaExceededError("API Key quota exceeded")

    # 3. 子Key配额
    if context.sub_key:
        sub_remaining = context.sub_key.quota_total - context.sub_key.quota_used
        if sub_remaining < estimated_cost:
            raise QuotaExceededError("Sub Key quota exceeded")
```

---

## 成本计算

### Token 计数

```python
class BillingCalculator:
    """计费计算器"""

    async def calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        channel_id: str
    ) -> Decimal:
        """计算请求成本"""

        # 获取模型配置
        model_config = await self.get_model_config(channel_id, model)

        # 计算成本
        input_cost = Decimal(prompt_tokens) * model_config.input_price_per_1k / 1000
        output_cost = Decimal(completion_tokens) * model_config.output_price_per_1k / 1000

        return input_cost + output_cost

    def estimate_cost(
        self,
        model: str,
        prompt: str,
        max_tokens: int
    ) -> Decimal:
        """预估成本 (用于预检查)"""
        # 使用简单的字符计数估算
        estimated_prompt_tokens = len(prompt) // 4

        # 获取默认价格
        default_prices = {
            "gpt-4o": (Decimal("0.005"), Decimal("0.015")),
            "gpt-3.5-turbo": (Decimal("0.0005"), Decimal("0.0015")),
            "claude-3-sonnet": (Decimal("0.003"), Decimal("0.015")),
        }

        input_price, output_price = default_prices.get(
            model,
            (Decimal("0.01"), Decimal("0.03"))
        )

        return (Decimal(estimated_prompt_tokens) * input_price / 1000 +
                Decimal(max_tokens) * output_price / 1000)
```

---

## 账单生成

### 发票数据结构

```python
@dataclass
class BillingLineItem:
    """账单明细项"""
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    total: Decimal

@dataclass
class Invoice:
    """发票"""
    id: str
    tenant_id: str
    period_start: datetime
    period_end: datetime
    line_items: List[BillingLineItem]
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    status: InvoiceStatus  # draft, pending, paid, overdue

class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
```

### 发票生成

```python
class BillingCalculator:
    async def generate_invoice(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime
    ) -> Invoice:
        """生成账单"""

        # 获取期间内的使用记录
        usage_records = await self.get_usage_records(
            tenant_id, period_start, period_end
        )

        # 按模型聚合
        model_totals = defaultdict(lambda: {"tokens": 0, "cost": Decimal(0)})
        for record in usage_records:
            model_totals[record.model_name]["tokens"] += record.total_tokens
            model_totals[record.model_name]["cost"] += Decimal(record.cost_usd)

        # 生成明细项
        line_items = []
        for model, data in model_totals.items():
            line_items.append(BillingLineItem(
                description=f"API Usage - {model}",
                quantity=Decimal(data["tokens"]),
                unit="tokens",
                unit_price=Decimal(data["cost"]) / Decimal(data["tokens"]) * 1000,
                total=data["cost"]
            ))

        # 计算小计和税费
        subtotal = sum(item.total for item in line_items)
        tax = subtotal * self.tax_rate
        total = subtotal + tax

        return Invoice(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            line_items=line_items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            status=InvoiceStatus.DRAFT
        )
```

---

## 用量报表

### 报表生成

```python
class UsageReport:
    """用量报表"""

    async def generate(
        self,
        tenant_id: str,
        start_date: date,
        end_date: date,
        group_by: str = "model"
    ) -> UsageStatistics:
        """生成用量报表"""

        query = select(UsageLog).where(
            UsageLog.tenant_id == tenant_id,
            UsageLog.created_at >= start_date,
            UsageLog.created_at < end_date
        )

        logs = await self.db.execute(query)
        records = logs.all()

        # 统计
        total_requests = len(records)
        total_tokens = sum(r.total_tokens for r in records)
        total_cost = sum(Decimal(r.cost_usd) for r in records)
        avg_latency = sum(r.latency_ms for r in records) / total_requests if total_requests else 0
        success_rate = sum(1 for r in records if r.status == "success") / total_requests if total_requests else 0

        # 分组统计
        if group_by == "model":
            by_group = self._group_by_model(records)
        elif group_by == "date":
            by_group = self._group_by_date(records)
        elif group_by == "channel":
            by_group = self._group_by_channel(records)
        else:
            by_group = self._group_by_key(records)

        return UsageStatistics(
            total_requests=total_requests,
            total_tokens=total_tokens,
            total_cost=total_cost,
            avg_latency_ms=avg_latency,
            success_rate=success_rate,
            by_model=by_group if group_by == "model" else [],
            by_date=by_group if group_by == "date" else [],
            by_channel=by_group if group_by == "channel" else [],
            by_key=by_group if group_by == "key" else []
        )
```

### 报表导出

```python
class DataExporter:
    """数据导出器"""

    async def export_csv(
        self,
        records: List[UsageLog],
        output_path: str
    ):
        """导出为 CSV"""
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)

            # 写入表头
            writer.writerow([
                'request_id', 'model', 'prompt_tokens',
                'completion_tokens', 'total_tokens',
                'cost_usd', 'latency_ms', 'status',
                'created_at'
            ])

            # 写入数据
            for record in records:
                writer.writerow([
                    record.request_id,
                    record.model_name,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    record.cost_usd,
                    record.latency_ms,
                    record.status,
                    record.created_at.isoformat()
                ])
```

---

## 冷热分离

### 数据分层

```
┌─────────────────────────────────────────────────────┐
│                     热 数据                          │
│              (7天内 - PostgreSQL)                    │
│  - 完整日志内容                                      │
│  - 快速查询                                          │
│  - 实时统计                                          │
└─────────────────────────────────────────────────────┘
                         │
                         │ 7天后迁移
                         ▼
┌─────────────────────────────────────────────────────┐
│                     温 数据                          │
│              (7-30天 - PostgreSQL)                   │
│  - 仅保留关键字段                                    │
│  - 压缩存储                                          │
│  - 聚合统计                                          │
└─────────────────────────────────────────────────────┘
                         │
                         │ 30天后迁移
                         ▼
┌─────────────────────────────────────────────────────┐
│                     冷 数据                          │
│            (30天+ - 对象存储 Parquet)                │
│  - Parquet 格式                                      │
│  - 低成本存储                                        │
│  - 归档查询                                          │
└─────────────────────────────────────────────────────┘
```

### 冷存储管理

```python
class ColdStorageManager:
    """冷存储管理器"""

    async def archive_old_logs(self):
        """归档旧日志"""
        # 查找30天前的日志
        threshold = datetime.now(UTC) - timedelta(days=30)

        logs = await self.get_logs_before(threshold)
        if not logs:
            return

        # 转换为 Parquet
        parquet_path = await self.convert_to_parquet(logs)

        # 上传到对象存储
        await self.upload_to_s3(parquet_path, f"logs/{threshold.year}/{threshold.month}/")

        # 删除数据库中的记录
        await self.delete_archived_logs(threshold)

    async def convert_to_parquet(self, logs: List[UsageLog]) -> str:
        """转换为 Parquet 格式"""
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.Table.from_pydict({
            'id': [str(l.id) for l in logs],
            'request_id': [l.request_id for l in logs],
            'tenant_id': [str(l.tenant_id) for l in logs],
            'model_name': [l.model_name for l in logs],
            'prompt_tokens': [l.prompt_tokens for l in logs],
            'completion_tokens': [l.completion_tokens for l in logs],
            'total_tokens': [l.total_tokens for l in logs],
            'cost_usd': [l.cost_usd for l in logs],
            'latency_ms': [l.latency_ms for l in logs],
            'status': [l.status for l in logs],
            'created_at': [l.created_at for l in logs],
        })

        path = f"/tmp/logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        pq.write_table(table, path)
        return path
```

---

## 告警

### 配额告警

```python
class AlertManager:
    """告警管理器"""

    async def check_quota_alerts(self):
        """检查配额告警"""
        tenants = await self.get_all_tenants()

        for tenant in tenants:
            usage_percent = tenant.quota_used / tenant.quota_total * 100

            if usage_percent >= 90:
                await self.send_alert(
                    tenant_id=tenant.id,
                    alert_type="quota_critical",
                    message=f"Tenant {tenant.name} quota usage: {usage_percent:.1f}%"
                )
            elif usage_percent >= 80:
                await self.send_alert(
                    tenant_id=tenant.id,
                    alert_type="quota_warning",
                    message=f"Tenant {tenant.name} quota usage: {usage_percent:.1f}%"
                )
```

### 异常检测

```python
class AnomalyDetector:
    """异常检测器"""

    async def detect_usage_anomaly(self, tenant_id: str) -> List[Anomaly]:
        """检测用量异常"""
        # 获取历史数据
        history = await self.get_usage_history(tenant_id, days=30)

        # 计算基线
        baseline = {
            "daily_requests": np.mean([h.requests for h in history]),
            "daily_cost": np.mean([h.cost for h in history]),
        }

        # 检测当前数据
        today = await self.get_today_usage(tenant_id)

        anomalies = []

        # 请求量异常
        if today.requests > baseline["daily_requests"] * 3:
            anomalies.append(Anomaly(
                type="request_spike",
                severity="high",
                message=f"Request count {today.requests} > 3x baseline {baseline['daily_requests']:.0f}"
            ))

        # 成本异常
        if today.cost > baseline["daily_cost"] * 3:
            anomalies.append(Anomaly(
                type="cost_spike",
                severity="high",
                message=f"Daily cost ${today.cost:.2f} > 3x baseline ${baseline['daily_cost']:.2f}"
            ))

        return anomalies
```

---

*最后更新: 2026-03-10*
