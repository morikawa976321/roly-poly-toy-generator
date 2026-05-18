"""
backend.app サブパッケージ。

役割: FastAPI アプリと形状・物理・永続化モジュールの集約。
働き: ``main`` / ``api`` 経由で HTTP を提供。各モジュールは gene 生成から SQLite 保存まで相互に import される。
"""
