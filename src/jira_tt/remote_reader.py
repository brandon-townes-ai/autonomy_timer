"""SSH into vehicles and read remote files."""
import os
import subprocess
from dataclasses import dataclass



@dataclass
class VehicleConfig:
    host: str
    user: str
    port: int = 22


def load_vehicle_config(vehicle: str) -> VehicleConfig:
    """Load SSH config for *vehicle* (e.g. 'rap-107') from environment variables.

    Normalizes 'rap-107' -> 'RAP107' and reads VEHICLE_RAP107_HOST, etc.
    Raises EnvironmentError if HOST or USER are missing.
    """
    prefix = "VEHICLE_" + vehicle.upper().replace("-", "") + "_"

    host = os.environ.get(prefix + "HOST")
    user = os.environ.get(prefix + "USER")

    if not host:
        raise EnvironmentError(
            f"No SSH config for vehicle {vehicle}: missing {prefix}HOST"
        )
    if not user:
        raise EnvironmentError(
            f"No SSH config for vehicle {vehicle}: missing {prefix}USER"
        )

    port_str = os.environ.get(prefix + "PORT", "22")
    try:
        port = int(port_str)
    except ValueError:
        port = 22

    return VehicleConfig(host=host, user=user, port=port)


def is_sshpass_available() -> bool:
    return subprocess.run(["which", "sshpass"], capture_output=True).returncode == 0


def ssh_cat_file(
    remote_path: str,
    config: VehicleConfig,
    dry_run: bool = False,
    verbose: bool = False,
) -> str:
    """Cat *remote_path* over SSH and return the file contents as a string.

    Returns empty string when dry_run=True (command is printed instead).
    Raises subprocess.CalledProcessError on SSH or remote command failure.
    """
    password = os.environ.get("VEHICLE_SSH_PASSWORD")

    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new"]
    if config.port != 22:
        ssh_cmd += ["-p", str(config.port)]
    ssh_cmd += [f"{config.user}@{config.host}", f"cat {remote_path}"]

    sshpass_available = subprocess.run(
        ["which", "sshpass"], capture_output=True
    ).returncode == 0

    if password and sshpass_available:
        cmd = ["sshpass", "-p", password] + ssh_cmd
    else:
        cmd = ssh_cmd

    using_sshpass = password and sshpass_available
    display = ["sshpass", "-p", "***"] + ssh_cmd if using_sshpass else ssh_cmd

    if dry_run:
        print(f"  [dry-run] would run: {' '.join(display)}")
        return ""

    if verbose:
        if password and not sshpass_available:
            print("  [ssh] sshpass not found, falling back to plain SSH")
        print(f"  [ssh] {' '.join(display)}")

    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True)
    return result.stdout
