# Social Video Content Automation

MVP pipeline tạo **content package** cho video ngắn, kiểm tra các điều kiện an toàn cơ bản, lưu artifact và tùy chọn gửi tới publisher webhook. Hệ thống mặc định chạy `dry-run`; không scraping, không spam và không tự vượt qua chính sách/điều kiện kiếm tiền của nền tảng.

## Luồng

1. Chọn chủ đề từ `config/topics.json`.
2. Tạo tiêu đề, kịch bản, scene plan, caption, hashtag và disclosure.
3. Kiểm tra độ dài, từ khóa bị cấm và trường bắt buộc.
4. Tạo asset manifest, voice artifact và subtitle timing.
5. Render video 9:16 bằng FFmpeg, tạo `video.mp4`.
6. Chạy `ffprobe` QA và ghi `qa.json`.
7. Nếu `PUBLISH_MODE=webhook`, gửi JSON tới một adapter dùng API chính thức của nền tảng.

> Hệ thống chỉ tạo nội dung và gọi adapter được cấu hình. Việc tài khoản có đủ điều kiện kiếm tiền, được duyệt quảng cáo hay nhận thanh toán do từng nền tảng quyết định.

## Chạy local

```bash
PYTHONPATH=src python -m app --topic "mẹo học tiếng Anh" --output artifacts --render
```

Chế độ mặc định là `dry-run`. Để gọi publisher:

```bash
export PUBLISH_MODE=webhook
export PUBLISH_WEBHOOK_URL="https://your-approved-adapter.example/publish"
python -m app --topic "mẹo học tiếng Anh" --output artifacts
```

Không commit token/API key. Xem `.env.example`.

## GitHub Actions

Workflow `.github/workflows/generate-content.yml` chạy mỗi ngày và có thể chạy thủ công. Nó chỉ bật đăng thật khi chọn `publish=true` và secret `PUBLISH_WEBHOOK_URL` đã được cấu hình. Nên dùng webhook/adapter riêng gọi API chính thức của YouTube, TikTok, Instagram hoặc Facebook; không dùng thông tin đăng nhập trình duyệt.

## Mở rộng tiếp theo

- Thay `TemplateContentGenerator` bằng nhà cung cấp LLM được phê duyệt.
- Thêm renderer MP4 (FFmpeg/TTS) và kiểm tra bản quyền media.
- Viết adapter riêng cho từng nền tảng, giới hạn tốc độ và idempotency.
- Thêm bước duyệt người dùng trước khi publish và thu thập số liệu doanh thu hợp lệ.
