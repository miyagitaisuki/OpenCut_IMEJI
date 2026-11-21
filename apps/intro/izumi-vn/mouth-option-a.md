# Phương án A: Miệng có tham số (Izumi, Live2D)

Một bộ miệng duy nhất, điều khiển bằng hai tham số `ParamMouthOpenY` và `ParamMouthForm`. Khớp với `apps/intro/src/Live2dAvatar.tsx`, không cần sửa code.

## 1. Tham số và hình cần đạt

| Mora | `ParamMouthOpenY` | `ParamMouthForm` | Hình miệng |
|---|---|---|---|
| あ (a) | 1.00 | 0.30 | Mở to, thấy răng trên và lưỡi |
| い (i) | 0.30 | 1.00 | Mở hẹp, kéo ngang |
| う (u) | 0.35 | -1.00 | Tròn nhỏ, chu môi |
| え (e) | 0.55 | 0.70 | Mở vừa, khóe kéo nhẹ |
| お (o) | 0.75 | -0.70 | Tròn, mở vừa-to |
| ん, っ, pause, ま ば ぱ | 0.00 | 0.00 | Đóng, đường ω |

Thang: `ParamMouthOpenY` 0 → 1, `ParamMouthForm` -1 → 1. Đặt keyform tại các điểm trên, nội suy tuyến tính giữa chúng.

## 2. Layer liên quan

- `Mouth_Inside`: trong miệng (răng trên, lưỡi). Hiện chỉ 116 px, cần vẽ lại bản mở.
- `Mouth_LipUpper`, `Mouth_LipLower`: môi trên và dưới, deform theo hai tham số.
- Thứ tự lớp giữ nguyên như brief: `Mouth_Inside` → `Mouth_LipLower` → `Mouth_LipUpper`.

## 3. Prompt tạo art

### Prompt 1: miệng mở ở trạng thái あ (keyform chính)
```
Flat vector anime chibi mouth, single shape, for a Live2D rig. Open mouth saying "a" (あ), wide and open, facing front.
Style: solid color fills only, no gradients, no highlights, no textures, no grain, no translucent shading.
Uniform dark brown outline #4A2A1F, same line weight as a clean flat vector icon.
Colors: mouth interior #7D3B38, tongue #E67E7E, upper teeth white #FFFFFF with a thin #4A2A1F separation line.
Show the upper teeth row at the top of the opening and the tongue at the bottom. Mouth fills about 60% of a 1000×600 px area, centered, on a solid green #00A84A background.
Output as a separate single-object image, no other elements.
```

### Prompt 2: môi trên và môi dưới ở trạng thái trung tính
```
Flat vector anime chibi lips, two separate shapes: upper lip and lower lip, for a Live2D rig. Neutral resting position, slightly parted.
Style: solid fills only, pink lips #F2B8A6 with a flat darker band #E8A090 for the lower lip, no gradient, no highlight.
Uniform dark brown outline #4A2A1F. Upper lip and lower lip each on a separate image, same scale, both centered on the same vertical axis, on solid green #00A84A background.
```

### Prompt 3: hình tham chiếu cho keyform i, u, o (chỉ để kiểm tra)
```
Three flat vector anime chibi mouths in a row, same style and size, for a Live2D rig:
1) "i" (い): wide flat smile, slight opening, corners pulled sideways.
2) "u" (う): small round pout, lips pushed forward.
3) "o" (お): round open mouth, medium size.
Solid fills only, uniform #4A2A1F outline, no gradient, same interior color #7D3B38, on solid green #00A84A.
```

Gửi kèm `Face.png` và miệng ω hiện tại làm tham chiếu khi chạy prompt.

## 4. Quy tắc khi nhận kết quả

- Không có gradient, highlight, hạt.
- Viền đều, cùng độ dày với các bộ phận khác.
- Kích thước miệng khoảng 0.14–0.25 chiều rộng mặt (theo bảng trong brief chính).
- Cùng canvas 2400 × 2800, đặt tâm tại khoảng (1200, 1340).
- Mỗi hình là một file PNG riêng, nền trong suốt khi tách.

## 5. Cách làm trong Cubism Editor

1. Đặt `Mouth_Inside` (trạng thái mở) và hai môi ở trạng thái trung tính.
2. Tạo deformer cho `Mouth_LipUpper` và `Mouth_LipLower`, gắn vào `ParamMouthOpenY` và `ParamMouthForm`.
3. Tạo keyform theo bảng mục 1. Với `ParamMouthOpenY = 0`, ẩn `Mouth_Inside` hoặc đặt opacity bằng 0.
4. Kiểm tra từng mora trong viewer.

## 6. Nghiệm thu

- [ ] Mở từng mora (あ い う え お ん), các hình miệng khác nhau rõ.
- [ ] Ở `ParamMouthOpenY = 0`, không thấy lớp bên trong miệng.
- [ ] Miệng đối xứng khi `ParamMouthForm` ở ±1, trừ hình u, o có chủ đích.
- [ ] Chuyển đổi đóng ↔ mở không có khoảng trống giữa hai môi.
- [ ] Chạy một đoạn audio ngắn: miệng đổi đúng nhịp âm tiết.

## 7. Bàn giao

- `.cmo3` / `.can3` có `ParamMouthOpenY` và `ParamMouthForm`.
- `.model3.json` xuất vào `public/avatars/izumi/`.
- Ghi chú: danh sách layer miệng đã vẽ lại.
