# Ba integration

Build từ common source bằng `python3 scripts/build_plugins.py`. Mỗi archive có
runtime riêng, provider.json, cấu hình hook phù hợp, script configure/doctor và
skill setup. Không cần npm, không cài package Python ngoài standard library.

| Provider | Cơ chế | Nơi cài |
|---|---|---|
| Codex desktop | .codex-plugin manifest + hooks | Local marketplace, review/trust hook |
| Claude Code | .claude-plugin manifest + hooks | Local marketplace hoặc --plugin-dir |
| Kiro CLI 2.x | Agent JSON riêng | .kiro/agents/rux-assistant.json |
| Kiro CLI V3 | Standalone hooks | .kiro/hooks/rux-assistant.json |
| Kiro IDE v1 | when/then hook flavor | .kiro/hooks/rux-assistant.json |

Không giả định mọi Kiro harness dùng cùng schema. Installer yêu cầu chọn flavor,
không đổi default agent hoặc quyền tools, và từ chối ghi đè cấu hình Rux khác nội
dung. Agent hook thiếu sự kiện permission thì không giả lập attention.

Cấu hình kết nối cần serial/IP, adb và project scope. Dữ liệu không nằm trong cache
plugin, không đóng gói vào ZIP. Mỗi chat một thư mục và bộ đếm sequence, Rux chọn
chat thay vì để plugin ưu tiên. Hook lỗi/offline luôn trả JSON trung lập và exit 0;
không block prompt/tool, không duyệt quyền thay người dùng và không ép model tiếp tục.

Xem [hướng dẫn chi tiết](../plugins/README.md) và [wire protocol](../plugins/PROTOCOL.md).
