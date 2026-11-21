# Instruction: Lip-sync theo âm tiết tiếng Nhật + sửa lỗi rig Izumi

Áp dụng cho file `izumi-rig-v5.psd` (31 layer). Mục tiêu: miệng đổi hình theo nguyên âm mora (あ い う え お), ん/っ/pause và ま ば ぱ là miệng đóng.

## 1. Mapping nguyên âm → tham số (khớp `apps/intro/src/Live2dAvatar.tsx`)

| Mora | Trạng thái | `ParamMouthOpenY` | `ParamMouthForm` | Hình miệng cần có |
|---|---|---|---|---|
| あ (a) | mở rộng | 1.00 | 0.30 | Mở to, thấy răng trên và lưỡi |
| い (i) | cười ngang | 0.30 | 1.00 | Mở hẹp, kéo ngang, khóe miệng xa |
| う (u) | chu môi | 0.35 | -1.00 | Miệng tròn nhỏ, môi chu ra |
| え (e) | vừa, hơi ngang | 0.55 | 0.70 | Mở vừa, khóe hơi kéo |
| お (o) | tròn, mở | 0.75 | -0.70 | Miệng tròn, mở vừa-to |
| ん, っ, pause, ま ば ぱ | đóng | 0.00 | 0.00 | Môi khép, thấy đường ω |

Quy ước: `ParamMouthOpenY` từ 0 đến 1, `ParamMouthForm` từ -1 đến 1. Đặt keyform tại các điểm trên, nội suy tuyến tính giữa chúng.

## 2. Cách làm art (chọn 1)

**Phương án A (khuyến nghị): một bộ miệng có tham số.** Dùng `Mouth_LipUpper`, `Mouth_LipLower`, `Mouth_Inside` và deform theo hai tham số trên. Cần:
- `Mouth_Inside` ở trạng thái mở, có răng trên và lưỡi, tối thiểu 300 px rộng ở trạng thái a.
- `Mouth_LipUpper`, `Mouth_LipLower` có đủ độ cong để chuyển từ ω (đóng) sang tròn (u, o) và ngang (i).
- Lớp trong miệng ẩn khi `ParamMouthOpenY = 0`, để không lộ khi đóng.

**Phương án B: mỗi âm một file PNG.** Vẽ 6 file: `Mouth_a`, `Mouth_i`, `Mouth_u`, `Mouth_e`, `Mouth_o`, `Mouth_n`, đặt cùng canvas và cùng tâm. Trong Cubism, mỗi file là một keyform của một tham số `ParamMouthShape` (0..5). Dễ kiểm soát hơn nhưng khó nội suy mượt giữa các hình.

## 3. Lỗi cần sửa (xếp theo ưu tiên)

1. **Miệng chỉ có trạng thái đóng (ω).** `Mouth_Inside` chỉ có 116 px, không đủ để làm trạng thái a/o. Vẽ lại bản mở theo mục 2A.
2. **`Tie` còn một phần đặc.** 75% pixel trong bbox là opaque, nhìn còn thấy khối. Xuất lại PNG trong suốt chỉ chứa cà vạt.
3. **Vết hạt tối phía sau cằm** (trong `HairBack` hoặc `HairSideL/R`). Vẽ lại vùng này dạng phẳng, không có họa tiết nhiễu.
4. **Mảng sáng trên trán bên trái** cạnh `HairFront`. Xóa hoặc vẽ lại bằng màu tóc.
5. **Má hồng dạng gradient** (layer `Face`). Thay bằng một hình màu `#F2B8A6` đặc, mép rõ.
6. **`EyelashL_Upper`, `EyelashR_Upper` phủ 36% bbox và có khối đặc.** Kiểm tra lại hình mi, bỏ khối đặc, giữ nét đều.
7. **Tên layer phải không có ký tự null.** Đã sửa trong v5, giữ nguyên khi xuất lại.
8. **Lông mày `BrowL`, `BrowR` có fill 9–10%.** Đúng với nét mảnh, chỉ kiểm tra độ dày đều hai bên.

## 4. Tiêu chí nghiệm thu

- [ ] Mở từng mora (あ い う え お ん) trong viewer Cubism, các hình miệng khác nhau rõ.
- [ ] Ở `ParamMouthOpenY = 0`, không thấy lớp bên trong miệng.
- [ ] Miệng đối xứng khi `ParamMouthForm` ở ±1 (trừ hình u, o có chủ đích).
- [ ] Chuyển động từ đóng sang mở không có khoảng trống giữa hai lớp môi.
- [ ] Kiểm tra với một đoạn audio ngắn: miệng đổi đúng nhịp với âm tiết.

## 5. Bàn giao

- File `.cmo3` / `.can3` đã có tham số `ParamMouthOpenY`, `ParamMouthForm` (phương án A) hoặc `ParamMouthShape` (phương án B).
- `.model3.json` xuất ra `public/avatars/izumi/`.
- Ghi chú: phương án đã chọn và danh sách layer đã sửa.
