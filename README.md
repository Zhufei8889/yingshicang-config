# 影视仓 / TVBox 配置自动更新聚合仓库

自用的影视仓 / TVBox 配置源聚合仓库:通过 GitHub Actions 定时自动抓取多个公开配置源,
把它们镜像聚合到本仓库,生成稳定的配置地址,供影视仓、TVBox、OK 影视等壳软件随时拉取。

> 所有配置均来自互联网公开分享,版权归原作者所有;本仓库仅做聚合与镜像,仅供学习交流,请勿商用。

## 一、使用地址

打开 App,进入「设置 → 配置地址」,粘贴下面任一地址:

| 类型 | 地址 | 说明 |
| --- | --- | --- |
| 多仓订阅(推荐) | `https://raw.githubusercontent.com/<你的用户名>/yingshicang-config/main/output/多仓订阅.json` | App 内可在各源之间切换 |
| 单仓聚合 | `https://raw.githubusercontent.com/<你的用户名>/yingshicang-config/main/output/单仓聚合.json` | 所有源站点合并成一个,开箱即用 |

> 把 `<你的用户名>` 换成你的 GitHub 用户名。仓库必须为 **公开(public)**,`raw.githubusercontent.com` 才能被 App 访问。

## 二、源可用性状态

<!-- STATUS:START -->
🔄 最近更新:尚未运行(推送仓库后由 GitHub Actions 自动生成)
<!-- STATUS:END -->

## 三、项目结构

```
yingshicang-config/
├── .github/workflows/update.yml   # GitHub Actions 定时更新工作流
├── config/sources.json            # 配置源列表(主地址 + 备用地址),可自行增删
├── scripts/update.py              # 核心脚本(下载→校验→合并→落盘→状态),零第三方依赖
├── output/                        # 更新产物(自动生成并提交)
│   ├── 多仓订阅.json              # 多仓聚合订阅(推荐)
│   ├── 单仓聚合.json              # 所有源 sites 合并成一个
│   ├── status.json                # 机器可读的各源状态
│   ├── shield.json                # shields.io 徽章数据
│   └── feimao.json / ...          # 各源独立配置
└── README.md
```

## 四、部署到 GitHub(三步)

1. **推送仓库**:把本目录推送到你自己的 GitHub 仓库(公开)。
2. **启用 Actions**:仓库 → Actions → 确认启用工作流(仓库内已含 `.github/workflows/update.yml`)。
3. **等待首次运行**:推送后会自动触发一次;也可在 Actions → "Auto Update TVBox Configs" → Run workflow 手动运行。

默认每天 **02:00、14:00(UTC,即北京时间 10:00、22:00)** 自动更新一次,结果自动提交回 `main` 分支。

## 五、自定义配置源

编辑 `config/sources.json`:

```json
{
  "sources": [
    {
      "id": "feimao",
      "name": "肥猫",
      "urls": ["http://肥猫.net/tv", "http://备用地址/tv"]
    }
  ]
}
```

- `id`:输出文件名(建议英文小写,如 `feimao`)。
- `name`:展示名称。
- `urls`:依次尝试的地址列表,第一个成功的会被使用;主地址在前、备用在后。

修改后推送到 `main` 分支会自动触发一次更新。

## 六、本地运行(可选)

脚本只使用 Python 标准库,**无需安装任何依赖**(Python 3.8+ 即可):

```bash
# Linux / macOS
GITHUB_REPOSITORY=你的用户名/yingshicang-config python scripts/update.py

# Windows PowerShell
$env:GITHUB_REPOSITORY="你的用户名/yingshicang-config"; python scripts/update.py
```

## 七、常见问题

- **某个源一直失败?** 多数源做了地区/频率限制,本地与 GitHub Actions 网络环境不同,可能此通彼不通。脚本会按 `urls` 顺序自动尝试所有备用地址。
- **国内访问 raw 地址慢?** 可在地址前套一层 `ghproxy` 等加速前缀。
- **会死循环提交吗?** 不会。`push` 触发只监听 `config/`、`scripts/` 与工作流文件的变更,自动提交只改 `output/` 与 README 状态区,不会再次触发。

## 八、免责声明

本项目仅用于学习、测试与个人使用;聚合的接口资源来自互联网公开分享,版权归原作者所有。若涉及侵权,请联系删除相应内容。
