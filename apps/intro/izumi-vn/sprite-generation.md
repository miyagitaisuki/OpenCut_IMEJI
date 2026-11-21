# Brief sinh ảnh sprite: biểu cảm, cử chỉ, trang phục (Izumi, visual novel video)

## 1. Mục tiêu
Sinh bộ sprite PNG nửa thân (từ thắt lưng trở lên) cho nhân vật Izumi, dùng trong khung visual novel video. Mỗi ảnh là một tổ hợp: **biểu cảm × cử chỉ tay × trang phục**. Trang phục tách thành lớp riêng để đổi được.

## 2. Ảnh tham chiếu (identity anchor)
- **Anchor chính:** `images/7.png` (cười nhẹ, ôm sách). Dùng làm ảnh tham chiếu cho mọi lần sinh, để giữ tóc, mắt, khuôn mặt, tỉ lệ đầu.
- Phụ: `images/5.png` (khoanh tay, giận), `images/8.png` (ôm sách, ngượng), `images/6.png` (vẫy tay).
- Mọi lần sinh phải đính kèm anchor. Không sinh từ prompt chữ thuần.

## 3. Thông số kỹ thuật
- Canvas: **1024 × 1024** (sinh), nền **trong suốt** hoặc trắng `#FFFFFF` (sẽ tách sau).
- **Đường cắt:** y = 700 px (tính từ đỉnh canvas). Áo không cần thấy dưới thắt lưng, không thấy chân.
- Nhân vật chiếm khoảng 60–65% chiều cao khung từ đỉnh tóc tới đường cắt.
- Vị trí: đầu hơi lệch cao, căn giữa theo trục dọc. Giữ cùng tỉ lệ đầu với anchor.
- Định dạng xuất: PNG, RGBA, không nén mất dữ liệu.

## 4. Lớp (layer) để đổi trang phục
Mục tiêu: một bộ **body** dùng chung, và các bộ **outfit** thay được.

| Lớp | Nội dung | Ghi chú |
|---|---|---|
| `body` | tóc, mặt, cổ, tay, da | Dùng chung cho mọi trang phục |
| `outfit` | áo khoác, cà vạt, váy (phần trên thắt lưng) | Đổi theo bộ đồng phục |
| `prop` | sách, vật cầm tay | Tùy cảnh; có thể ẩn |

**Cách làm (thực tế):** AI không sinh lớp riêng đáng tin. Hai cách:
1. **(Khuyến nghị) Sinh ảnh đầy đủ, rồi tách bằng màu:** sinh mọi tổ hợp với đồng phục navy. Tách `outfit` = vùng áo (navy/đen/trắng sơ mi) bằng ngưỡng màu; phần còn lại là `body`. Kiểm tra mép ở vai và tay, sửa tay nếu bị lẫn.
2. Sinh riêng `outfit` với cùng tư thế, nền trắng, rồi ghép. Dễ lệch hơn; chỉ dùng khi cần đổi áo khác hẳn.

Khi đổi trang phục, chỉ cần thay lớp `outfit`, giữ nguyên `body`.

## 5. Danh sách biểu cảm (E)
| Mã | Biểu cảm | Mô tả ngắn |
|---|---|---|
| E01 | neutral | Mặt bình thường, miệng khép |
| E02 | smile | Cười nhẹ, miệng ω |
| E03 | happy | Cười mở miệng, mắt sáng |
| E04 | angry | Chân mày nhíu, mắt sắc, môi mím |
| E05 | sad | Chân mày cụp, mắt buồn |
| E06 | shy | Mặt đỏ, mắt né, ngượng |
| E07 | surprised | Mắt mở to, miệng tròn |
| E08 | worried | Chân mày nhíu nhẹ, lo lắng |
| E09 | thinking | Mắt nhìn lên, miệng hơi mím |
| E10 | wink | Một mắt nhắm |

## 6. Danh sách cử chỉ tay (G)
| Mã | Cử chỉ | Ghi chú |
|---|---|---|
| G01 | hands at sides | Hai tay thõng, mặc định |
| G02 | arms crossed | Khoanh tay (như ảnh 5) |
| G03 | wave | Một tay vẫy lên cao (như ảnh 6) |
| G04 | hug book | Ôm sách trước ngực (như ảnh 7, 8) |
| G05 | hold book | Cầm sách một bên |
| G06 | point up | Một ngón trỏ chỉ lên |
| G07 | point side | Tay chỉ sang bên (phải hoặc trái nhân vật) |
| G08 | thumbs up | Ngón cái lên |
| G09 | hand on chest | Tay đặt lên ngực |
| G10 | shrug | Hai tay mở ra, nhún vai |
| G11 | clap | Hai tay vỗ trước ngực |

## 7. Trang phục (O)
| Mã | Trang phục | Mô tả |
|---|---|---|
| O01 | uniform_navy | Đồng phục hiện tại: áo khoác navy, sơ mi trắng, cà vạt xanh sọc |
| O02 | uniform_grey | Cùng kiểu, màu xám |
| O03 | casual_white | Áo sơ mi trắng, không khoác |

Mỗi O thay màu, giữ cùng kiểu cắt. Không đổi tóc hoặc khuôn mặt.

## 8. Mẫu prompt
Tiếng Anh cho công cụ tạo ảnh. Đính kèm `7.png` làm reference.

```
Same chibi anime girl as the reference image: same face, same brown wavy shoulder-length hair, same big brown eyes, same proportions and head size.
Upper body only, cropped at the waist. No legs visible.
Expression: {EXPRESSION}.
Hand gesture: {GESTURE}.
Outfit: {OUTFIT}.
Flat clean anime style, soft colors, thin dark-brown outline, plain white background, centered, same scale as reference.
```

Negative: `legs, feet, text, watermark, extra fingers, distorted hands, different hair, different face, cropped head`.

Ví dụ:
- E04 + G02 + O01: `angry expression with furrowed brows; arms crossed in front of chest; navy blazer uniform with white collar and striped blue tie`.

## 9. Quy tắc đặt tên
`{outfit}_{expression}_{gesture}.png`, ví dụ `O01_E04_G02.png`. Dùng mã số để tránh sai khi ghép trong code. Bảng tra mã ở mục 5–7.

Lưu kèm file `manifest.json`: mã → ý nghĩa, và ghi lại prompt đã dùng.

## 10. Kiểm tra từng ảnh
- [ ] Khuôn mặt, tóc, tỉ lệ đầu giống anchor.
- [ ] Không có chân, không có chữ, không có watermark.
- [ ] Tay đủ số ngón, không méo.
- [ ] Cắt đúng y = 700 (sau khi chuẩn hóa), không cắt đầu.
- [ ] Biểu cảm đọc được ở kích thước nhỏ (khoảng 300 px chiều cao).
- [ ] Trang phục tách lớp được: mép áo không lẫn vào da.

## 11. Xử lý sau khi sinh
1. Xóa nền trắng, giữ RGBA.
2. Chuẩn hóa: crop đường y = 700, căn đầu cùng một vị trí.
3. Tách `outfit` bằng ngưỡng màu, xuất `body` và `outfit` riêng cho mỗi O.
4. Đặt vào `sprites/` theo tên ở mục 9.

## 12. Phạm vi và giới hạn
- Brief này không yêu cầu miệng theo âm (lip-sync) cho từng ảnh. Lip-sync sẽ làm bằng cách hiện/ẩn hoặc thay miệng riêng sau.
- Không đảm bảo tuyệt đối nhất quán giữa các lần sinh. Cần kiểm tra và loại ảnh lệch.
- Bản quyền: chỉ dùng ảnh do bạn tạo hoặc có quyền dùng.
