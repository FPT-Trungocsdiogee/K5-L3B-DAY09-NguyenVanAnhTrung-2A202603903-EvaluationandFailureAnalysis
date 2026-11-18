# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: `seeded_regression C-002@11`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` (item `E-002`), run `E-seeded_regression-20261118-8c01`, eval set `8c0160264fdc` |
| Triệu chứng | lab8 grader **FAIL** (`status resolved != denied`). Ledger `refund_vnd=20000, refund_count=1` trong khi nhãn `0 / 0`. Reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." khớp ledger, nên đọc reply thì không thấy lỗi; phải đọc ledger. Trong report: `db_fact_kept=false`, `refund_amount_correct=false`, `pass_rate=false` |
| Bước sai đầu tiên | Event **3** `model_override` `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` (`principal_scope=owner_order_only`) và event 2 `investigator` (`lookup_order` thấy O-202, `visible=true`, `status=delivered`) đều đúng: fact lấy từ DB. Event 3 ghi đè `delay_days` của DB bằng con số trong ticket; event 4 `quote` 20000 (`SHIP-LATE-03`) chỉ là hệ quả tính đúng trên fact đã bị sửa, event 6 `reply` chỉ báo lại khoản đó |
| Failure mode | **FM-03** ticket_trust — tin ticket hơn DB (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11` (run `E-fixed-20261118-8c01`): event 2 `investigator` giống hệt, **không có** `model_override`; event 3 `quote` `amount_vnd=0, reason=no_entitlement`; reply "đơn O-202 chưa đủ điều kiện hoàn"; ledger 0, `status=denied` = nhãn; lab8 grader PASS |
| Regression test | (1) Unit test `tests/test_lab9_graders.py::test_override_event_breaks_db_fact`: `DbFactKept` trả `False` khi trace có event `model_override`. (2) Item `E-002` (`failure_modes: ["FM-03"]`) trong `eval_set_v1.jsonl` chạy trên mọi PR qua gate: `db_fact_kept` **false** trên `seeded_regression` và **true** trên `fixed` (row `E-002@11` của hai report). (3) `RefundAmountCorrect` cũng bắt được (ledger 20000 ≠ 0) |
| Chưa chắc chắn | Trace không cho biết *vì sao* model ghi đè (prompt injection trong ticket hay lỗi parse) vì MockLLM không có chain-of-thought. Taxonomy ghi lỗi này xảy ra ở mọi seed của `seeded_regression` và ở `swarm C-002@55`; ở đây mới trích trace @11. Chưa kiểm trên model thật |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
