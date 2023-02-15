#!/usr/bin/env bash
set -eo pipefail

RED='\033[1;31m'
NC='\033[0m' # No Color
FORK=automaticrippingmachine
TAG=latest
function usage() {
    echo -e "\nUsage: docker_setup.sh [OPTIONS]"
    echo -e " -f <fork>\tSpecify the fork to pull from on DockerHub. \n\t\tDefault is \"$FORK\""
    echo -e " -t <tag>\tSpecify the tag to pull from on DockerHub. \n\t\tDefault is \"$TAG\""
}

# parse script arguments
while getopts 'f:t:' OPTION
do
    case $OPTION in
    f)    FORK=$OPTARG
          ;;
    t)    TAG=$OPTARG
          ;;
    ?)    usage
          exit 2
          ;;
    esac
done
IMAGE="$FORK/automatic-ripping-machine:$TAG"

function remove_existing_arm() {
    # Remove thick-client installation artifacts
    ## Check if the ArmUI service exists in any state and remove it
    if sudo systemctl list-unit-files --type service | grep -F armui.service; then
        echo -e "${RED}Previous installation of ARM service found. Removing...${NC}"
        service=armui.service
        sudo systemctl stop $service && sudo systemctl disable $service
        sudo find /etc/systemd/system/$service -delete
        sudo systemctl daemon-reload && sudo systemctl reset-failed
    fi

    ## Check if the ARM codebase is installed
    cd /opt
    if [ -d arm ]; then
        echo -e "${RED}Existing ARM installation found, removing...${NC}"
        sudo rm -rf arm
    fi

    ## Check if old logging rules are installed
    if [ -f /etc/rsyslog.d/30-arm.conf ]; then
        echo -e "${RED}ARM syslog rule found. Removing...${NC}"
        sudo rm /etc/rsyslog.d/30-arm.conf
    fi
}

function install_reqs() {
    apt update -y && apt upgrade -y
    apt install -y curl lsscsi
}

function add_arm_user() {
    echo -e "${RED}Adding arm user${NC}"
    # create arm group if it doesn't already exist
    if ! [[ "$(getent group arm)" ]]; then
        groupadd arm
    else
        echo -e "${RED}arm group already exists, skipping...${NC}"
    fi

    # create arm user if it doesn't already exist
    if ! id arm >/dev/null 2>&1; then
        useradd -m arm -g arm
        passwd arm
    else
        echo -e "${RED}arm user already exists, skipping...${NC}"
    fi
    usermod -aG cdrom,video arm
}

function launch_setup() {
    # install docker
    if [ -e /usr/bin/docker ]; then
        echo -e "${RED}Docker installation detected, skipping...${NC}"
    else
        echo -e "${RED}Installing Docker${NC}"
        # the convenience script auto-detects OS and handles install accordingly
        curl -sSL https://get.docker.com | bash
        usermod -aG docker arm
    fi
}

function pull_image() {
    echo -e "${RED}Pulling image from $IMAGE${NC}"
    sudo -u arm docker pull "$IMAGE"
}

function setup_mountpoints() {
    echo -e "${RED}Creating mount points${NC}"
    for dev in /dev/sr?; do
        sudo mkdir -p "/mnt$dev"
    done
    sudo chown arm:arm /mnt/dev/sr*
}

function save_start_command() {
    url="https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/v2_devel/scripts/docker/start_arm_container.sh"
    cd ~arm
    sudo -u arm wget -O start_arm_container.sh "$url"
    chmod +x start_arm_container.sh
    sed -i "s|IMAGE_NAME|${IMAGE}|" start_arm_container.sh
    # TODO: auto populate/remove ARM_UID AND ARM_GID
    # TODO: prompt num cpus to use (or auto-configure? How to print num cpu CORES)
    # TODO: Auto-add entries for each sr?
}

# start here
remove_existing_arm

install_reqs
add_arm_user
launch_setup
pull_image
setup_mountpoints
save_start_command

cd ~arm
echo -e "${RED}Installation complete. A template command to run the ARM container is located in: $(pwd) ${NC}"
