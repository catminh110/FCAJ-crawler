#!/usr/bin/env python3
"""
CLI management tool for FCAJ Crawler EC2 instance.
Usage:
    python deploy/manage_ec2.py status
    python deploy/manage_ec2.py start
    python deploy/manage_ec2.py stop
    python deploy/manage_ec2.py reboot
    python deploy/manage_ec2.py url
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
INSTANCE_FILE = WORKSPACE / "data" / "ec2_instance.json"
PROFILE = "agent-toolkit"
REGION = "us-east-1"


def get_instance_info():
    if not INSTANCE_FILE.exists():
        print("❌ Chưa tìm thấy file thông tin máy ảo tại data/ec2_instance.json")
        print("Máy ảo có thể chưa được khởi tạo!")
        sys.exit(1)
    with open(INSTANCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_instance_info(data):
    INSTANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INSTANCE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_aws_cmd(args):
    cmd = ["aws"] + args + ["--profile", PROFILE, "--region", REGION, "--output", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ Lỗi AWS CLI: {res.stderr}")
        sys.exit(res.returncode)
    try:
        return json.loads(res.stdout) if res.stdout.strip() else {}
    except json.JSONDecodeError:
        return res.stdout


def fetch_remote_status(instance_id):
    data = run_aws_cmd(["ec2", "describe-instances", "--instance-ids", instance_id])
    reservations = data.get("Reservations", [])
    if not reservations:
        return None
    instances = reservations[0].get("Instances", [])
    return instances[0] if instances else None


def cmd_status(args):
    info = get_instance_info()
    inst_id = info["instance_id"]
    print(f"🔍 Đang kiểm tra trạng thái máy ảo EC2 ({inst_id})...")
    remote = fetch_remote_status(inst_id)
    if not remote:
        print(f"❌ Không tìm thấy máy ảo {inst_id} trên AWS!")
        return

    state = remote["State"]["Name"]
    pub_ip = remote.get("PublicIpAddress", "Chưa có IP công khai")
    dns = remote.get("PublicDnsName", "")
    inst_type = remote.get("InstanceType", "")

    # Update cache
    info["state"] = state
    info["public_ip"] = pub_ip
    info["public_dns"] = dns
    save_instance_info(info)

    print("\n" + "=" * 55)
    print("📊 THÔNG TIN MÁY CHỦ FCAJ CRAWLER TRÊN AWS EC2")
    print("=" * 55)
    print(f"• Instance ID   : {inst_id}")
    print(f"• Cấu hình      : {inst_type} (2 vCPU, 2GB RAM)")
    print(f"• Trạng thái    : {state.upper()}")
    print(f"• Địa chỉ IP    : {pub_ip}")
    if state == "running":
        print(f"• Link Web App  : http://{pub_ip}/")
        print(f"• Link Dashboard: http://{pub_ip}:5000/")
    else:
        print(f"• Lưu ý         : Máy đang tắt ({state}), không bị tính tiền CPU/RAM.")
        print(f"                  Chạy 'python deploy/manage_ec2.py start' để bật lại.")
    print("=" * 55 + "\n")


def cmd_start(args):
    info = get_instance_info()
    inst_id = info["instance_id"]
    print(f"🚀 Đang gửi lệnh bật máy ảo ({inst_id})...")
    run_aws_cmd(["ec2", "start-instances", "--instance-ids", inst_id])
    print("⏳ Đang chờ máy ảo khởi động và cấp IP công khai...")
    run_aws_cmd(["ec2", "wait", "instance-running", "--instance-ids", inst_id])
    cmd_status(args)


def cmd_stop(args):
    info = get_instance_info()
    inst_id = info["instance_id"]
    print(f"🛑 Đang gửi lệnh tắt máy ảo ({inst_id}) để tiết kiệm credit...")
    run_aws_cmd(["ec2", "stop-instances", "--instance-ids", inst_id])
    print("⏳ Đang chờ máy ảo dừng hoàn toàn...")
    run_aws_cmd(["ec2", "wait", "instance-stopped", "--instance-ids", inst_id])
    print(f"✅ Đã dừng máy ảo {inst_id} thành công! Không còn tính phí CPU/RAM.")


def cmd_reboot(args):
    info = get_instance_info()
    inst_id = info["instance_id"]
    print(f"🔄 Đang khởi động lại máy ảo ({inst_id})...")
    run_aws_cmd(["ec2", "reboot-instances", "--instance-ids", inst_id])
    print("✅ Đã gửi lệnh khởi động lại thành công.")


def cmd_url(args):
    info = get_instance_info()
    inst_id = info["instance_id"]
    remote = fetch_remote_status(inst_id)
    if remote and remote["State"]["Name"] == "running":
        pub_ip = remote.get("PublicIpAddress")
        if pub_ip:
            print(f"http://{pub_ip}/")
            return
    print(f"http://{info.get('public_ip', '127.0.0.1')}/")


def main():
    parser = argparse.ArgumentParser(description="Quản lý máy ảo FCAJ Crawler trên AWS EC2")
    sub = parser.add_subparsers(dest="command", help="Lệnh thực hiện")
    sub.add_parser("status", help="Xem trạng thái máy ảo và link web")
    sub.add_parser("start", help="Bật máy ảo EC2")
    sub.add_parser("stop", help="Tắt máy ảo EC2 để tiết kiệm chi phí")
    sub.add_parser("reboot", help="Khởi động lại máy ảo")
    sub.add_parser("url", help="In ra link web trực tiếp")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "status": cmd_status,
        "start": cmd_start,
        "stop": cmd_stop,
        "reboot": cmd_reboot,
        "url": cmd_url,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
