# N6 新手可用性研究协议

这是一项人工产品验收，不是自动化测试。维护者不得代填结果，也不得在任务过程中口头带做。

## 参与者

- 至少 5 名此前没有使用过 PySTG 的目标用户；
- 每人使用同一候选版本、同一入门资料和干净项目；
- 研究员只读任务说明和记录观察，不解释按钮位置或实现概念；
- 软件崩溃、错误提示、求助、返回重做和误操作均原样记录。

## 三个计时任务

1. 10 分钟内，从新 Pattern 选择预设、调整精确参数并完成正式预览。
2. 30 分钟内，从“道中骨架”完成两波内容，并配置全灭后续。
3. 60 分钟内，从“两阶段 Boss 骨架”完成两个阶段、一次背景转场和一次事件反应；全程不写脚本。

每项从参与者开始阅读任务卡计时，到正式预览中可观察到目标行为为止。超时仍继续记录最终时间和失败点。

## 必须记录

每名参与者独立记录：匿名 ID、是否有 PySTG 经验、三项用时和完成状态、是否写脚本、求助次数、失败点。维护者口头指导发生一次即整份研究不通过。

结果保存为 `reports/n6_usability.json`，字段示例：

```json
{
  "study": "pystg-n6",
  "maintainer_coaching": false,
  "participants": [
    {
      "id": "anonymous-01",
      "prior_pystg_experience": false,
      "pattern_minutes": 8.5,
      "midstage_minutes": 24,
      "boss_minutes": 51,
      "completed_pattern": true,
      "completed_midstage": true,
      "completed_boss_background_event": true,
      "wrote_script": false,
      "help_requests": 0,
      "failure_points": []
    }
  ]
}
```

验收命令：

```powershell
python tools/verify_n6_usability.py reports/n6_usability.json
```

通过条件是至少 4/5 人分别达到 10、30、60 分钟阈值。报告需要由非实现者独立复核原始记录后提交；自动构造的 fixture 只能验证报告格式，不能作为 N6.4 证据。
