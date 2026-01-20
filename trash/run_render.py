import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 直接导入main函数
from src.render.__init__ import main

if __name__ == "__main__":
    main()
