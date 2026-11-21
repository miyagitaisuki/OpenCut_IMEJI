# Hình minh họa: Minna bài 5

Tạo từng hình bằng Gemini (Google AI Pro), tải về và **đặt đúng tên file** vào thư mục `images/` cạnh file `minna-05.visuals.json` (ở bài mẫu: `apps/intro/scenes/images/`; bài thật: `lessons/<ten>/images/`).

**Cách dùng:** dán *Phong cách chung* + *Prompt* của từng hình vào Gemini. Chọn tỉ lệ **4:3** hoặc vuông. Nếu hình có chữ thì yêu cầu tạo lại ("no text").

**Phong cách chung (dán kèm mỗi prompt):**
> Cute flat vector illustration, soft pastel palette (IMEJI blue #bfdbfe, navy #1e3a8a, mint #d0fae5, light yellow #fef3c6), simple rounded shapes, gentle shading, plain off-white background, centered subject with margin, no text, no letters, no logos, friendly anime-inspired style suitable for a Japanese lesson for beginners.

| # | File | Câu ví dụ | Prompt |
|---|---|---|---|
| 1 | `library.png` | 図書館へ行きます。 | A young student walking toward a small library building with books on the sign, an arrow on the ground pointing to the door. |
| 2 | `osaka.png` | 来週、大阪へ行きます。 | A traveler with a small suitcase looking at Osaka Castle in the distance, a dotted path with an arrow leading there. |
| 3 | `home.png` | 七時に家へ帰ります。 | A tired office worker walking home in the evening toward a cozy house with lit windows, a wall clock showing 7 o'clock. |
| 4 | `train.png` | 電車で会社へ行きます。 | A businessperson riding a clean Japanese commuter train, seen from the side, office buildings outside the window. |
| 5 | `bicycle.png` | 自転車で学校へ行きます。 | A high school student in uniform riding a bicycle toward a school building. |
| 6 | `airplane.png` | 飛行機で日本へ来ました。 | A passenger airplane flying over Mount Fuji with a few clouds. |
| 7 | `cinema.png` | 友達と映画館へ行きます。 | Two friends holding hands, smiling, walking into a movie theater with popcorn. |
| 8 | `family.png` | 家族と日本へ来ました。 | A family of four (parents and two children) holding hands at an airport arrivals gate with a cherry blossom poster. |
| 9 | `teacher.png` | 先生と図書館へ行きます。 | A kind teacher and a student walking side by side into a library, the teacher holding books. |

Khi có đủ hình: chạy `node scripts/lesson.ts check scenes/minna-05.visuals.json scenes/minna-05.script.vi.txt`. Lệnh sẽ hết báo "picture missing". Hình nào còn thiếu thì video vẫn render được, thẻ ví dụ đó hiện không có hình.
