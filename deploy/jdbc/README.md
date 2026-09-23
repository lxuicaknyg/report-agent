# JDBC 驱动 jar

openLooKeng 没有 SQLAlchemy 方言，只能走 JDBC，需要厂商的驱动 jar。把 jar
放在这个目录下，它会以只读方式挂载到后端容器的 `/opt/jdbc`。

前端「数据源」表单里的**「JDBC 驱动 jar 路径」填容器内路径**：

```
/opt/jdbc/hetu-jdbc-1.0.0.jar
```

不是宿主机路径 —— 这是这一项最容易填错的地方。

jar 文件本身不提交进仓库（`.gitignore` 里已忽略 `*.jar`），部署时随镜像包
一起搬进内网。

JRE 已经装在后端镜像里（`openjdk-17-jre-headless`），不需要另外准备 Java。
这里只放驱动 jar。

用不到 openLooKeng 的话，把 `docker-compose.yml` 里 `/opt/jdbc` 这个挂载删掉
即可，MySQL 和 GaussDB 不受影响。
