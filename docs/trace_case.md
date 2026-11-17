# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11` (item E-014), run ID `E-seeded_regression-20261117-4ede` trong `src/reports/eval_seeded_regression.json` |
| Triệu chứng | Grader Lab 8 FAIL `proposal_mismatch`. Trong report, dòng E-014@11 có `refund_amount_correct`=False, `proposal_amount_correct`=False, `reply_matches_ledger`=False, `pass_rate`=False. **Ledger ghi 90.000** (label 120.000), nhưng reply vẫn nói "Dạ, LogiX đã hoàn 120.000đ cho đơn O-515.", tức trôi chảy và sai. |
| Bước sai đầu tiên | Event **#5 `proposal`** `{"amount_vnd": 120000}` |
| Vì sao là bước *đầu tiên* | #1 `handoff` đúng contract. #2 `investigator` đọc đúng O-515 từ DB (`delivered_late`, trễ 5 ngày, hỏng đã verify). #3 `quote` 150.000 đúng luật: lấy số lớn nhất giữa SHIP-LATE-03 30.000 và DMG-04 150.000, bằng label `proposal_amount`. #4 `refund_history` `refunded_vnd`=30.000 là lookup chỉ đọc và đúng với dữ liệu (khoản hoàn trước C-HIST-515). Bước #5 là lần đầu agent dùng số đó để tự trừ: 150.000 − 30.000 = 120.000, rồi đưa 120.000 cho host thay vì quote đầy đủ. Host trừ tiếp 30.000 theo trần đơn, nên ledger còn 90.000. |
| Failure mode | **FM-05** pre_deducted. Hệ quả thứ cấp là reply nói 120.000 trong khi ledger 90.000, cùng triệu chứng FM-08, nhưng nguyên nhân gốc là #5. |
| Đối chứng | `fixed C-014@11`: #1 `handoff`, #2 `investigator`, #3 `quote` 150.000, #4 `reply` "đã hoàn 120.000đ". Không có event `refund_history` và `proposal`: quote 150.000 đi thẳng vào host, host trừ 30.000 → ledger 120.000 = label, grader Lab 8 PASS. Cùng câu reply "120.000đ" nhưng ở đây reply đúng, vì ledger thật sự là 120.000. |
| Regression test | `src/tests/test_lab9_trace_case.py` (marker `student`, CI chạy qua `-k "lab9 and not advanced"`). `test_first_wrong_step_is_the_pre_deducted_proposal`: kiểm thứ tự event và payload #3/#4/#5, và kiểm `fixed` không có `proposal`. `test_graders_catch_c014_regression[seeded_regression]`: `RefundAmountCorrect`, `ProposalAmountCorrect`, `ReplyMatchesLedger` đều trả False. `[fixed]`: cả ba trả True. Đã chạy: 3 passed (fail trên variant lỗi, pass trên `fixed`). |
| Chưa chắc chắn | Trace không có event cho lời gọi `issue_refund` / quyết định của host, nên việc "host trừ lần hai" được suy ra từ ledger (90.000 = 120.000 − 30.000) và luật trần theo đơn trong `lab8/policy.py` (`cap_per_order`), không đọc trực tiếp từ trace. Trace cũng không cho biết vì sao agent gọi `refund_history`. Cả 5 seed của E-014 đều fail giống nhau trong report, nên lỗi không phụ thuộc seed. |

Tái hiện:
```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
python -m lab9.trace_case --shape fixed --claim C-014 --seed 11   # đối chứng
python -m pytest -q -o addopts= tests/test_lab9_trace_case.py
```

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
