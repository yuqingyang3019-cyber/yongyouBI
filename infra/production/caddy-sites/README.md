# 独立应用子域名

每个独立应用在此目录新增一个以 `.caddy` 结尾的文件，Caddy 会自动导入。

示例 `new-app.caddy`：

```caddy
newapp.water-healer.com {
    reverse_proxy new-app:3000
}
```

独立应用的 Compose 文件必须将其公网服务加入已存在的共享网络：

```yaml
services:
  new-app:
    networks:
      - edge

networks:
  edge:
    external: true
    name: water-healer-edge
```

不要为 `new-app` 配置宿主机 `ports`；Caddy 是唯一公网入口。为该子域名配置 DNS A 记录到 ECS 后，Caddy 会自动申请 HTTPS 证书。
