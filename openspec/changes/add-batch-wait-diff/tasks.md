## 1. Batch Orchestrator

- [ ] 1.1 实现 `hand.batch.run` 的请求模型、步骤调度与逐步结果结构
- [ ] 1.2 让 batch 内的 `move`、`click`、`drag`、`scroll`、`type`、`press`、`wait`、`capture` 全部复用现有执行管线
- [ ] 1.3 实现 `stop_on_error` 的 fail-fast 与继续执行两种模式

## 2. Wait 与 Diff

- [ ] 2.1 实现 `hand.wait` 的固定时长等待语义，并接入 batch 步骤
- [ ] 2.2 实现 `hand.capture.diff` 的 capture 查询、像素比较与确定性摘要

## 3. 验证

- [ ] 3.1 为 batch 顺序执行、fail-fast、非法步骤类型与审计关联编写测试
- [ ] 3.2 为固定时长等待与 capture diff 的成功、缺失 capture、边界比例计算编写测试
