# Ming Atelier MVP

线上测试版部署包。这个目录只包含独立站 MVP 必要代码，不包含原项目里的客户报告、书籍、临时文件或私人资料。

## 功能

- Ming Atelier / 命理工坊平台首页
- MVP 视觉定稿页：`/design-lock.html`
- 免费八字排盘
- 免费版 PDF 总结报告
- 命盘图，包含神煞和地支关系
- 年月日时起卦
- 本地历史记录
- 商品/咨询承接位

## 本地运行

```bash
pip install -r requirements.txt
python auto_report_app/server.py
```

打开：

```text
http://127.0.0.1:8765
```

## Render 部署

推荐用 Docker Web Service。

1. 把本目录上传到一个新的 GitHub 仓库。
2. 在 Render 新建 Web Service，连接该仓库。
3. Environment 选择 Docker。
4. Health Check Path 使用：

```text
/api/health
```

5. 部署成功后先用 Render 临时域名测试。

上线前先检查：

```text
/design-lock.html
```

设计定稿采用 Four Pillars Mark、黑金命盘主视觉、英文主品牌、中文副标、免费报告轻量化、深度报告产品化的方向。

## 当前限制

- 这是 MVP 免费版，不是正式付费深度报告。
- 本地文件存储会随平台重启或重新部署丢失，正式版需要数据库或对象存储。
- 暂未接登录、支付、订单、邮件、正式商城。
