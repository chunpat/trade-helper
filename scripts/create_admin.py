#!/usr/bin/env python3
"""
创建管理员账号脚本
"""
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.risk_control import User
from app.core.security import hash_password

def create_admin_user(username: str = "admin", password: str = "admin123", is_admin: bool = True):
    """
    创建管理员账号
    
    Args:
        username: 用户名，默认为 'admin'
        password: 密码，默认为 'admin123'
        is_admin: 是否为管理员，默认为 True
    """
    load_dotenv()
    
    db: Session = SessionLocal()
    
    try:
        # 检查用户是否已存在
        existing_user = db.query(User).filter(User.username == username).first()
        
        if existing_user:
            print(f"⚠️  用户 '{username}' 已存在！")
            response = input("是否要更新密码？(y/N): ").strip().lower()
            
            if response == 'y':
                existing_user.password_hash = hash_password(password)
                existing_user.is_admin = is_admin
                existing_user.is_active = True
                db.commit()
                print(f"✅ 用户 '{username}' 密码已更新！")
            else:
                print("取消操作。")
            return
        
        # 创建新用户
        new_user = User(
            username=username,
            password_hash=hash_password(password),
            is_active=True,
            is_admin=is_admin
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        print(f"✅ 管理员账号创建成功！")
        print(f"   用户名: {username}")
        print(f"   密码: {password}")
        print(f"   管理员权限: {'是' if is_admin else '否'}")
        print(f"\n⚠️  请登录后立即修改密码！")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 创建管理员账号失败: {str(e)}")
        sys.exit(1)
    finally:
        db.close()

def main():
    """主函数"""
    print("=" * 50)
    print("创建管理员账号")
    print("=" * 50)
    
    # 交互式输入
    print("\n请输入管理员信息（直接回车使用默认值）:")
    
    username = input("用户名 [admin]: ").strip() or "admin"
    password = input("密码 [admin123]: ").strip() or "admin123"
    
    is_admin_input = input("是否为管理员 [Y/n]: ").strip().lower()
    is_admin = is_admin_input != 'n'
    
    print(f"\n将创建以下账号:")
    print(f"  用户名: {username}")
    print(f"  密码: {'*' * len(password)}")
    print(f"  管理员: {'是' if is_admin else '否'}")
    
    confirm = input("\n确认创建？(Y/n): ").strip().lower()
    
    if confirm == 'n':
        print("取消创建。")
        return
    
    create_admin_user(username, password, is_admin)

if __name__ == "__main__":
    main()
