# Prompt tạo kịch bản mẫu cho cảnh visual novel Izumi (prototype)

Dán toàn bộ khối "Prompt" bên dưới cho AI khác, kèm các file ở mục "File đính kèm".

## Prompt

```
Bạn soạn kịch bản mẫu cho một cảnh visual novel video bài học tiếng Nhật N5. Giáo viên là Izumi (vai [1]). Chỉ có một người nói, Izumi.

Chủ đề: phân biệt 「は」và「が」, ngữ pháp N5.

Yêu cầu:
- Đúng 4 dòng thoại, Izumi nói cả 4 dòng. Mỗi dòng ngắn, dưới 30 chữ tiếng Nhật.
- Dòng 1: chào và nêu bài học.
- Dòng 2: đưa ví dụ 「わたしは学生{がくせい}です」 và nói 「は」đánh dấu chủ đề.
- Dòng 3: nói 「が」đánh dấu chủ ngữ (câu trả lời hoặc thông tin mới).
- Dòng 4: cảnh báo lỗi dùng sai trợ từ làm đổi nghĩa câu.
- Sau 4 dòng có 1 câu hỏi trắc nghiệm, 3 lựa chọn, 1 đáp án đúng, chọn đáp án đúng là lựa chọn A. Lựa chọn là câu tiếng Nhật hoàn chỉnh, sai ở trợ từ.
- Câu ví dụ tự viết. Không chép nguyên văn hội thoại hay bài tập từ giáo trình Minna no Nihongo.
- Chữ Hán có furigana theo cú pháp 漢字{かな}, kể cả trong lựa chọn và câu hỏi.
- Ghi tiếng Việt cho từng dòng sau dấu //, dịch tự nhiên và ngắn.
- Mỗi dòng thoại một câu, không gạch đầu dòng.

Trả về hai phần:

Phần A. Kịch bản, theo định dạng:
[1] 日本語 // bản dịch tiếng Việt

Phần B. Khối JSON cảnh, theo đúng mẫu sau (thay nội dung, giữ nguyên tên trường):
{
  "template": "vn",
  "sprite": "izumi-vn/O01_E01_G01.png",
  "lines": [
    { "who": "いずみ先生{せんせい}", "text": "..." },
    { "who": "いずみ先生{せんせい}", "text": "...", "sprite": "izumi-vn/O01_E02_G01.png" },
    { "who": "いずみ先生{せんせい}", "text": "..." },
    { "who": "いずみ先生{せんせい}", "text": "...", "sprite": "izumi-vn/O01_E04_G01.png" }
  ],
  "choice": { "question": "...", "options": ["...", "...", "..."], "answer": 0 }
}

Biểu cảm chỉ được chọn trong: O01_E01_G01 (bình thường), O01_E02_G01 (cười nhẹ), O01_E04_G01 (nghiêm, nhắc lỗi). Không dùng biểu cảm khác.

Không thêm lời giải thích ngoài hai phần trên.
```

## File đính kèm

| File | Để làm gì |
|---|---|
| `apps/intro/src/lesson/types.ts` (mục `VnScene`) | Định nghĩa trường của cảnh vn |
| `apps/intro/scenes/vn-prototype.json` | Ví dụ cảnh vn đã dựng, dùng làm mẫu định dạng |
| `.claude/skills/soan-bai-video/SKILL.md` (mục "Vai") | Quy tắc soạn kịch bản: giọng, furigana, bản quyền |
| `scripts/lesson_voices.json` | Giọng: vai 1 = Izumi (cùng giọng textts với まい cũ) |

Sprite có sẵn để chọn: `O01_E01_G01.png`, `O01_E02_G01.png`, `O01_E04_G01.png` (trong `apps/intro/public/izumi-vn/`). Các biểu cảm E03, E05–E08 đã có trong `apps/intro/izumi-vn/assets/sprites/` nhưng chưa được chép vào `public/`.
