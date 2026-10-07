---
name: refund-policy
description: Xét một yêu cầu hoàn tiền có đủ điều kiện hay không theo chính sách hoàn tiền trong data/policies/, chọn đúng chính sách theo ngày mua và tính phí hoàn tiền. Dùng khi người dùng hỏi về hoàn tiền, trả hàng lấy lại tiền, đơn hàng có được hoàn không hoặc phí hoàn tiền.
---

# Refund policy

Hướng dẫn xét yêu cầu hoàn tiền dựa trên tài liệu chính sách trong workspace. Chỉ dùng `list_files` và `read_file`; không cần chạy lệnh.

## Thông tin bắt buộc

Cần đủ 3 thông tin trước khi kết luận:

- **Ngày mua** (ngày cụ thể).
- **Ngày yêu cầu hoàn tiền** (ngày cụ thể). "Hôm nay" chỉ dùng được khi người dùng nói rõ ngày hôm nay.
- **Trạng thái kích hoạt**: sản phẩm đã kích hoạt hay chưa.

Nếu thiếu hoặc không rõ bất kỳ thông tin nào, hỏi lại đúng thông tin còn thiếu và dừng. Không giả định, không đưa ra kết luận tạm. Có thể tìm và đọc chính sách trước khi hỏi, nhưng không trả lời đủ/không đủ điều kiện. Nếu ngày yêu cầu sớm hơn ngày mua, hỏi lại để xác nhận.

Giá trị đơn hàng không bắt buộc: chỉ cần khi tính phí ra số tiền.

## Các bước

1. Kiểm tra đủ 3 thông tin bắt buộc. Thiếu thì hỏi lại (xem trên).
2. Tìm tài liệu: gọi `list_files` với `data/policies`. Không đoán tên file. Nếu thư mục không tồn tại hoặc không có tài liệu, báo cho người dùng và dừng.
3. Đọc từng tài liệu chính sách bằng `read_file`. Với mỗi tài liệu, ghi nhận **phạm vi hiệu lực** (áp dụng cho ngày mua nào), thời hạn được yêu cầu hoàn, phí hoàn tiền và các điều kiện loại trừ.
4. Chọn chính sách theo **ngày mua** (không theo ngày yêu cầu hoàn): chọn tài liệu có phạm vi hiệu lực chứa ngày mua, chú ý ranh giới "trước" (không gồm ngày đó) và "từ … bao gồm ngày này". Nếu không có tài liệu nào khớp hoặc có nhiều hơn một tài liệu khớp, báo rõ và dừng; không tự chọn.
5. Tính **số ngày đã qua** = ngày yêu cầu hoàn − ngày mua (ngày mua là ngày 0; ví dụ mua 2026-10-01, yêu cầu 2026-10-08 là 7 ngày). Còn trong thời hạn khi số ngày đã qua ≤ số ngày cho phép của chính sách.
6. Kết luận theo đúng chính sách đã chọn:
   - Vi phạm điều kiện loại trừ (ví dụ sản phẩm đã kích hoạt) → **Không đủ điều kiện**, dù còn trong thời hạn.
   - Quá thời hạn → **Không đủ điều kiện**.
   - Còn lại → **Đủ điều kiện**.
   Nêu mọi lý do không đạt, không chỉ lý do đầu tiên.
7. Phí: chỉ nêu khi đủ điều kiện, lấy đúng mức phí trong tài liệu (ghi "Không thu phí" nếu chính sách nói vậy). Nếu có giá trị đơn hàng thì tính ra số tiền phí và số tiền hoàn lại; nếu không có thì nêu tỷ lệ.
8. Đọc template `references/answer-template.md` trong thư mục skill này, tức `skills/refund-policy/references/answer-template.md`, và trả lời đúng các mục của template.

## Nguyên tắc

- Mọi con số (thời hạn, phí, ngày hiệu lực) phải lấy từ tài liệu đã đọc thành công trong lượt này hoặc các lượt trước; không dùng kiến thức chung về chính sách hoàn tiền.
- Nếu `read_file` hoặc `list_files` trả lỗi, báo lỗi và không kết luận.
- Chỉ ghi file khi người dùng yêu cầu; khi đó dùng `write_file` dưới `output/`.
