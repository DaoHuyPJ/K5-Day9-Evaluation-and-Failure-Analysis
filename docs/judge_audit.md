# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

```bash
cd src
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10      # exit 0
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 21   # exit 1
```

FAIL là lớp positive (việc của judge là tìm lỗi). Backend: REPLAY (verdict judge lưu sẵn trong CSV).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (`PASS floors`) | **dùng** |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt κ và R (`FAIL floors`) | **loại** |

Ma trận nhầm lẫn (output của `lab9.judge`):

| Tiêu chí | tp | fp | fn | tn | Specificity | Tỉ lệ FAIL judge quan sát | Rogan-Gladen hiệu chỉnh | Tỉ lệ FAIL theo người |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 66/70 = 0.943 | 0.28 | 0.30 | 30/100 = 0.30 |
| helpful | 9 | 0 | 21 | 70 | 70/70 = 1.000 | 0.09 | 0.30 | 30/100 = 0.30 |

## ≥5 case audit thủ công
tone_ok: cả 10 bất đồng. helpful: 3 ca đại diện cho 2 nhóm lỗi judge bỏ sót.

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú: sửa rubric thế nào |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách khiếu nại. Rubric: bắt buộc xưng "LogiX" / "anh/chị"; "em", "nha", "bạn ơi" = FAIL. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người | Cùng lỗi xưng hô như #1 ("bạn ơi", "nha"); có "Dạ" ở đầu câu không cứu được. Thêm ví dụ âm tính này vào rubric. |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ thấy "Dạ, vui lòng". Rubric: từ lịch sự không bù cho câu ra lệnh / gạt khách ("không cần nhắn thêm") = FAIL. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric: lời xin lỗi **không bắt buộc**; ngắn mà đủ ý (số tiền, thời gian, kính ngữ) = PASS. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Rubric: thêm danh sách từ tiếng Anh được phép ("refund"), không phạt. |
| 6 | H-063 "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống. Rubric: không được hứa ngoài kết quả hệ thống = FAIL; phần số tiền vẫn do code chấm (`reply_matches_ledger`), không giao cho judge. |
| 7 | H-070 "Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric: emoji trong ngữ cảnh khiếu nại = FAIL. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Theo ghi chú: nhãn người sai (người gán nhãn đọc nhầm ticket). Hành động: sửa nhãn người ở vòng gán nhãn sau, không sửa rubric. Không sửa CSV công khai ở bài này vì số tham chiếu (κ 0.757) và test tính trên file gốc. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ." | FAIL | PASS | Người | Lặp "Dạ" do lỗi gõ. Rubric: lỗi gõ nhỏ / lặp tiểu từ không làm hỏng giọng thì không FAIL. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien." | PASS | FAIL | Người | Dịch máy, mất dấu tiếng Việt. Rubric: reply tiếng Việt không dấu = FAIL. |
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Sai tiền. Judge chỉ đọc reply, không thấy ledger, nên **không thể** bắt lỗi này dù sửa rubric. Chuyển sang grader code `reply_matches_ledger` (FM-08). |
| 12 | HL-016 xin lỗi dài + "đã hoàn 55.000đ cho đơn O-404" (ledger 35.000đ) | PASS | FAIL | Người | Câu xin lỗi trôi chảy che lỗi sai tiền. 18/21 ca judge bỏ sót là "sai tiền" (đọc cột `human_failure`). Hành động giống #11. |
| 13 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Sai xưng hô (3/21 ca: HL-047, HL-091, HL-097). Đây là lỗi giọng: để judge tone (đã calibrate) chấm, không để judge helpful chấm. |

## Kết luận
- **tone_ok dùng được:** κ=0.757, P=0.857, R=0.800, đều trên FLOORS. Tỉ lệ FAIL quan sát 0.28; Rogan-Gladen hiệu chỉnh ra 0.30, đúng bằng tỉ lệ FAIL theo nhãn người (30/100). Judge vẫn bỏ sót 6/30 lỗi giọng (fn) và báo nhầm 4/70 (fp), nên chỉ dùng làm tín hiệu chất lượng, không dùng cho tiền hay approval.
- **helpful bị loại** (dẫn ma trận nhầm lẫn tp=9, fp=0, fn=21, tn=70): R=0.300 < 0.7 và κ=0.375 < 0.6. Precision 1.0 dễ gây hiểu lầm: judge chỉ FAIL các reply lỗi hiển nhiên (lạc đề, cụt, không hỏi mã đơn) và cho PASS 21/30 reply lỗi. Trong 21 ca đó, 18 ca là sai tiền: judge không có ledger nên không có cách nào kiểm.
- **Vì sao không dùng helpful làm gate:** nếu dùng, gate sẽ cho qua khoảng 70% reply lỗi (recall 0.3). Tỉ lệ lỗi quan sát 0.09, sau hiệu chỉnh Rogan-Gladen là 0.30, tức judge báo thấp hơn thực tế khoảng 3 lần. Số tiền trong reply phải chấm bằng code so với ledger (`reply_matches_ledger`, FM-08), đúng quy tắc "tiền và approval luôn chấm bằng code".
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí), nên các số trên có thể lạc quan hơn thực tế. Cần nhãn người mới làm held-out thật trước khi tin κ. Rubric sửa theo bảng audit phải được đo lại trên tập held-out đó. Một nhãn người đã biết là sai (H-081) cần sửa ở vòng gán nhãn sau.
