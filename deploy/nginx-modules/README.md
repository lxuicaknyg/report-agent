# 其他团队工具的路由

这个目录挂载到网关容器的 `/etc/nginx/workspace-modules/`，里面每个 `.conf`
文件给一个工具配一条路由。放在这里而不是打进镜像，是为了接入一个新工具时不用
重新构建、重新分发前端镜像。

**只有 `.conf` 结尾的文件会生效。** 下面的示例文件叫 `their-tool.conf.example`，
所以默认是不生效的；照着复制一份改名成 `<工具名>.conf` 即可。

改完之后不用重启容器，热加载就行：

```bash
docker compose exec gateway nginx -t        # 先验证语法，别把网关配挂了
docker compose exec gateway nginx -s reload
```

## 约定

路径命名空间是 `/api/<工具名>/v1/`，和工具自己的前端模块 key 保持一致。
命名空间不能和宿主的 `report` 撞，也不能和别的工具撞。

前端那边怎么写见 `frontend/CONTRIBUTING_MODULES.md`。
