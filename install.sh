#!/bin/bash
#
# Install script for Waveshare CM4 Double-Deck NAS Controller
# Sets up system dependencies, Python packages, and optionally configures autostart
#

set -e

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory (for absolute paths)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/nas-display.service"

# Default values
AUTOSTART=""
NETWORK_INTERFACE="end0"
DISK0_ID="sda"
DISK1_ID="sdb"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Install script for Waveshare CM4 Double-Deck NAS Controller"
    echo ""
    echo "Options:"
    echo "  --help          Show this help message"
    echo "  --autostart     Configure systemd service for autostart"
    echo "  --no-autostart  Skip autostart configuration"
    echo ""
    echo "If no autostart option is provided, you will be prompted interactively."
    exit 0
}

print_status() {
    echo -e "${BLUE}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[+]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[-]${NC} $1"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            usage
            ;;
        --autostart)
            AUTOSTART="yes"
            shift
            ;;
        --no-autostart)
            AUTOSTART="no"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Check for root privileges
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

echo ""
echo "=========================================="
echo " NAS Display Controller - Installation"
echo "=========================================="
echo ""

# Install system dependencies
print_status "Updating package lists..."
apt-get update -qq

print_status "Installing system dependencies..."
apt-get install -y python3-pip python3-pil python3-numpy smartmontools

print_success "System dependencies installed"

# Install Python packages
print_status "Installing Python packages..."
pip3 install --break-system-packages -r "${SCRIPT_DIR}/requirements.txt" 2>/dev/null || \
    pip3 install -r "${SCRIPT_DIR}/requirements.txt"

print_success "Python packages installed"

# Check SPI configuration
print_status "Checking SPI configuration..."
SPI_ENABLED=false

# Check both possible config file locations
for config_file in /boot/config.txt /boot/firmware/config.txt; do
    if [[ -f "$config_file" ]]; then
        if grep -q "^dtparam=spi=on" "$config_file" 2>/dev/null; then
            SPI_ENABLED=true
            break
        fi
    fi
done

if $SPI_ENABLED; then
    print_success "SPI interface is enabled"
else
    print_warning "SPI interface may not be enabled!"
    echo ""
    echo "  To enable SPI, run: sudo raspi-config"
    echo "  Navigate to: Interface Options -> SPI -> Enable"
    echo "  Then reboot your Raspberry Pi"
    echo ""
fi

# Autostart configuration
configure_autostart() {
    echo ""
    print_status "Configuring autostart service..."
    echo ""

    # Prompt for environment variables
    read -p "Network interface [${NETWORK_INTERFACE}]: " input
    NETWORK_INTERFACE="${input:-$NETWORK_INTERFACE}"

    read -p "First disk ID [${DISK0_ID}]: " input
    DISK0_ID="${input:-$DISK0_ID}"

    read -p "Second disk ID [${DISK1_ID}]: " input
    DISK1_ID="${input:-$DISK1_ID}"

    echo ""
    print_status "Creating systemd service..."

    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=NAS Display Controller
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}/controller
Environment="NAS_NETWORK_INTERFACE=${NETWORK_INTERFACE}"
Environment="NAS_DISK0_ID=${DISK0_ID}"
Environment="NAS_DISK1_ID=${DISK1_ID}"
ExecStart=/usr/bin/python3 main.py
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
EOF

    print_status "Enabling and starting service..."
    systemctl daemon-reload
    systemctl enable nas-display
    systemctl start nas-display

    print_success "Autostart configured and service started"
}

# Handle autostart option
if [[ -z "$AUTOSTART" ]]; then
    # Interactive mode
    echo ""
    read -p "Configure autostart on boot? [Y/n]: " response
    case "$response" in
        [nN][oO]|[nN])
            AUTOSTART="no"
            ;;
        *)
            AUTOSTART="yes"
            ;;
    esac
fi

if [[ "$AUTOSTART" == "yes" ]]; then
    configure_autostart
else
    print_status "Skipping autostart configuration"
fi

# Summary
echo ""
echo "=========================================="
echo " Installation Complete"
echo "=========================================="
echo ""
print_success "Dependencies installed successfully"

if [[ "$AUTOSTART" == "yes" ]]; then
    print_success "Autostart service configured"
    echo ""
    echo "  Service commands:"
    echo "    sudo systemctl status nas-display   # Check status"
    echo "    sudo systemctl restart nas-display  # Restart service"
    echo "    sudo systemctl stop nas-display     # Stop service"
    echo "    sudo journalctl -u nas-display -f   # View logs"
else
    echo ""
    echo "  To run manually:"
    echo "    cd ${SCRIPT_DIR}/controller"
    echo "    sudo python3 main.py"
    echo ""
    echo "  To configure autostart later, run:"
    echo "    sudo $0 --autostart"
fi

echo ""
