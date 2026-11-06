# 科研采购课程交付包
## 已整理
- docs/访谈资料：三轮训练角色事件访谈原文与整理、六角色历史事实摘录（Markdown、JSON、CSV）。摘录不是六人逐字稿。
- docs/流程图：改造前后两张PNG；行业分析、需求与追溯、设计、报价ROI和运行手册均提供Word及Markdown。
- Test：五类受控模拟自动测试数据、量化方案、每类过程图和Word；执行方法见量化方案。
- src：源码入口、演示地址与公网部署状态；实际代码位于仓库 src/my_tool。
## 仍缺材料及验收
六人完整原始访谈、四份平台原始简报、可公网访问的正式部署地址、企业真实数据和真实验收都未取得；不能以模拟事实、localhost或模拟测试结果替代。请在可访问平台和服务器后补齐，且勿将令牌、密码或真实敏感数据提交仓库。
## 生成与复测
python scripts/run_course_tests.py
安装python-docx与Pillow后，运行 python scripts/build_course_delivery.py。运行环境需要Windows中文字体。
