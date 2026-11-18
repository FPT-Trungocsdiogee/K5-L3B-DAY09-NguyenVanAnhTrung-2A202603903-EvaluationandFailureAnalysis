# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend REPLAY, verdict judge lưu sẵn trong CSV). Positive = `FAIL` (judge bắt được reply lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (exit 0) | **dùng** |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** κ và R (exit 1) | **loại** |

Ma trận nhầm lẫn (lệnh in ra):
- `tone_ok` (`data/eval/judge_tone_public.csv`): `tp=24, fp=4, fn=6, tn=66`; fail rate quan sát 0.28 → hiệu chỉnh Rogan–Gladen 0.30. 10 case bất đồng: 6 FN (H-008, H-017, H-029, H-063, H-070, H-094), 4 FP (H-042, H-051, H-081, H-088).
- `helpful` (`data/eval/judge_helpful_public.csv`): `tp=9, fp=0, fn=21, tn=70`; fail rate quan sát 0.09 → hiệu chỉnh 0.30. Theo cột `human_failure`, 30 reply người chấm FAIL gồm: **sai tiền 18** (judge PASS cả 18), sai xưng hô 3 (judge PASS cả 3), giọng cụt 4, không hỏi lại mã đơn 3, trả lời lạc đề 2 (judge bắt được cả 9).

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách; judge coi là thân thiện |
| 2 | tone H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người | Xưng "bạn" với khách lớn tuổi; judge coi là thân thiện |
| 3 | tone H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Giọng ra lệnh ("không cần nhắn thêm"); judge chỉ thấy "Dạ, vui lòng" |
| 4 | tone H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Ngắn nhưng đủ ý; judge phạt vì "thiếu xin lỗi" |
| 5 | tone H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | Từ "refund" được CS LogiX cho phép; judge phạt vì tiếng Anh |
| 6 | helpful HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | Người | Sai tiền: ledger ghi 40.000đ. Judge không thấy ledger nên không thể bắt |
| 7 | helpful HL-016 (xin lỗi dài + "đã hoàn 55.000đ cho đơn O-404") | PASS | FAIL | Người | Sai tiền: ledger ghi 35.000đ; câu xin lỗi dài làm judge chấm "helpful" |
| 8 | helpful HL-020 "Dạ, LogiX đã hoàn 90.000đ cho đơn O-303 ạ." | PASS | FAIL | Người | Sai tiền: ledger ghi 120.000đ |
| 9 | helpful HL-028 (xin lỗi lặp 2 lần + "đã hoàn 50.000đ cho đơn O-677") | PASS | FAIL | Người | Sai tiền: ledger ghi 35.000đ; lặp xin lỗi vẫn được judge PASS |
| 10 | helpful HL-035 (xin lỗi + "đã hoàn 50.000đ cho đơn O-303") | PASS | FAIL | Người | Sai tiền: ledger ghi 35.000đ |

Ở cả 10 case, người chấm đúng. Lỗi của judge `tone_ok` là lỗi văn phong (xưng hô, giọng ra lệnh, phạt nhầm từ được phép), sai lệch hai chiều nhưng vẫn trong FLOORS. Lỗi của judge `helpful` có hệ thống: mọi reply sai tiền đều bị PASS.

## Kết luận
- **Dùng `tone_ok`**: κ=0.757, P=0.857, R=0.80 đều vượt FLOORS. Chỉ dùng làm metric theo dõi văn phong, không dùng cho tiền/approval. Lưu ý 6 FN là xưng hô suồng sã/giọng ra lệnh: cần thêm ví dụ này vào rubric của judge.
- **Loại `helpful`**: R=0.30 (`fn=21` trên 30 FAIL) và κ=0.375 dưới sàn. 18/21 FN là **sai tiền**: judge chỉ đọc text reply, không có ledger, nên về bản chất không chấm được "đúng số tiền". Phần này đã được chấm bằng code: `RefundAmountCorrect` (ledger vs nhãn) và `ReplyLedgerMismatch` (FM-08, reply vs ledger). P=1.0 chỉ có nghĩa là judge ít báo nhầm, không bù được việc bỏ sót.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí); cần nhãn người mới để có held-out thật. Fail rate hiệu chỉnh (0.30) dựa trên R/specificity đo trên chính tập này.
