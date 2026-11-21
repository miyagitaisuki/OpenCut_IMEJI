# Sửa lỗi tóc sau (vết hạt) và mảng sáng trên trán

Áp dụng cho `izumi-rig-v8.psd`. Đã làm tạm trên v8: lọc median cho `HairBack` giúp giảm hạt, nhưng chưa đủ phẳng. Cần vẽ lại để đạt flat vector.

## 1. Vết hạt tối phía sau cằm (`HairBack`)

**Vị trí:** vùng tóc phía sau mặt, ngay dưới cằm, khoảng canvas (900–1500, 1100–1450). Ở đây có các layer `HairBack`, `Body_Skirt`, `Neck`, `Face` chồng lên nhau, và `HairBack` là nguồn hạt.

**Nguyên nhân:** `HairBack` có họa tiết nhiễu nâu sẫm, mô phỏng tóc kiểu tranh.

**Cách sửa:**
1. Vẽ lại `HairBack` dạng flat: màu nền `#9B745B`, một mảng bóng `#7A5641` theo đường tóc, một mảng sáng `#B38B71` ở đỉnh đầu. Không có hạt, không gradient.
2. Viền `#4A2A1F` đều, cùng độ dày với `HairFront`.
3. Kiểm tra: không còn điểm tối rời rạc khi phóng to 200%.

**Tạm thời (đã làm trên v8):** lọc median kích thước 9 trên màu `HairBack`. Hạt giảm nhưng viền có răng cưa nhẹ. Chỉ dùng để xem trước, không dùng làm bản cuối.

## 2. Mảng sáng trên trán bên trái (`Face` / `HairFront`)

**Vị trí:** cạnh trái đường chân tóc mái, khoảng canvas (840–880, 820–860).

**Nguyên nhân:** `Face` có vùng da (`#FCEEDF`) lộ ra vì `HairFront` không phủ hết đường chân tóc. Vùng này sáng hơn tóc xung quanh nên tạo thành một mảng.

**Cách sửa:**
1. Mở `HairFront`, vẽ thêm phần tóc phủ kín mép trên trái của trán, cùng màu tóc `#9B745B`, nối liền với đường chân tóc.
2. Hoặc, nếu muốn giữ trán sáng, bỏ mảng này trên `Face` và viền lại đường chân tóc cho khớp.
3. Kiểm tra không còn khe hở giữa `HairFront` và `Face` trên trán.

## 3. Kiểm tra kích thước miệng (đã đối chiếu)

Miệng mở `Mouth_Inside` rộng 172 px, `Face` rộng 991 px, tỉ lệ khoảng 0.17. Nằm trong khoảng 0.14–0.25 của brief miệng. Brief miệng (`mouth-option-a.md`) ghi "tối thiểu 300 px", con số đó không đúng với canvas 2400 px. Cần sửa lại thành "0.14–0.25 chiều rộng mặt".

## 4. Nghiệm thu

- [ ] Không còn hạt tối sau cằm khi phóng 200%.
- [ ] Không có khe sáng trên trán.
- [ ] Viền tóc đều, cùng độ dày với các bộ phận khác.
- [ ] Layer không có ký tự null trong tên.
