#!/bin/bash

# Deploy script for EDGE SERVER components
# Usage: ./deploy.sh [development|production]

set -euo pipefail

DEPLOY_ENV="${1:-development}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="/opt/edge-server"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

check_prerequisites() {
    log_step "Checking prerequisites..."
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
    
    # Check system requirements
    command -v python3 >/dev/null 2>&1 || { log_error "python3 is required"; exit 1; }
    command -v pip3 >/dev/null 2>&1 || { log_error "pip3 is required"; exit 1; }
    command -v nginx >/dev/null 2>&1 || { log_error "nginx is required"; exit 1; }
    command -v systemctl >/dev/null 2>&1 || { log_error "systemctl is required"; exit 1; }
    
    log_info "All prerequisites met"
}

create_users() {
    log_step "Creating system users..."
    
    # Create tunnel user
    if ! id "tunnel" >/dev/null 2>&1; then
        useradd -r -s /bin/false -d /opt/edge-server tunnel
        log_info "Created tunnel user"
    else
        log_info "tunnel user already exists"
    fi
    
    # Create webapp user
    if ! id "webapp" >/dev/null 2>&1; then
        useradd -r -s /bin/false -d /opt/edge-server webapp
        log_info "Created webapp user"
    else
        log_info "webapp user already exists"
    fi
}

setup_directories() {
    log_step "Setting up directories..."
    
    # Create main directory
    mkdir -p "$SERVER_DIR"
    mkdir -p "$SERVER_DIR/data"
    mkdir -p "$SERVER_DIR/logs"
    
    # Set permissions
    chown -R tunnel:tunnel "$SERVER_DIR"
    chown -R webapp:webapp "$SERVER_DIR/logs"
    
    # Allow webapp to write logs
    chmod g+w "$SERVER_DIR/logs"
    usermod -a -G tunnel webapp
    
    log_info "Directories created and permissions set"
}

install_application() {
    log_step "Installing application files..."
    
    # Copy Python files
    cp "$SCRIPT_DIR"/*.py "$SERVER_DIR/"
    cp -r "$SCRIPT_DIR/tunnel_system" "$SERVER_DIR/"
    
    # Copy configuration
    cp -r "$SCRIPT_DIR/config" "$SERVER_DIR/" 2>/dev/null || true
    
    # Install Python dependencies
    cd "$SERVER_DIR"
    pip3 install -r requirements.txt
    
    # Set permissions
    chown -R tunnel:tunnel "$SERVER_DIR"
    chmod +x "$SERVER_DIR"/*.py
    
    log_info "Application installed"
}

setup_systemd_services() {
    log_step "Setting up systemd services..."
    
    # Copy service files
    cp "$SCRIPT_DIR/systemd"/*.service /etc/systemd/system/
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable services
    systemctl enable tunnel-broker.service
    systemctl enable web-app.service
    
    log_info "Systemd services configured"
}

setup_nginx() {
    log_step "Setting up Nginx configuration..."
    
    # Copy nginx configuration
    cp "$SCRIPT_DIR/nginx/nginx.conf" /etc/nginx/nginx.conf
    cp "$SCRIPT_DIR/nginx/tunnel-broker.conf" /etc/nginx/sites-available/
    
    # Enable site
    ln -sf /etc/nginx/sites-available/tunnel-broker.conf /etc/nginx/sites-enabled/
    
    # Remove default site
    rm -f /etc/nginx/sites-enabled/default
    
    # Test nginx configuration
    nginx -t
    
    log_info "Nginx configured"
}

setup_ssl() {
    log_step "Setting up SSL certificates..."
    
    if [[ "$DEPLOY_ENV" == "production" ]]; then
        # Install certbot if not present
        if ! command -v certbot >/dev/null 2>&1; then
            log_info "Installing certbot..."
            apt-get update
            apt-get install -y certbot python3-certbot-nginx
        fi
        
        log_warn "Please run certbot manually after deployment:"
        log_warn "certbot --nginx -d your-domain.com"
    else
        # Create self-signed certificate for development
        mkdir -p /etc/nginx/ssl
        if [[ ! -f /etc/nginx/ssl/privkey.pem ]]; then
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout /etc/nginx/ssl/privkey.pem \
                -out /etc/nginx/ssl/fullchain.pem \
                -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
            log_info "Self-signed certificate created"
        fi
    fi
}

start_services() {
    log_step "Starting services..."
    
    # Start tunnel broker
    systemctl start tunnel-broker.service
    log_info "Tunnel broker started"
    
    # Wait a moment for tunnel broker to start
    sleep 3
    
    # Start web app
    systemctl start web-app.service  
    log_info "Web app started"
    
    # Restart nginx
    systemctl restart nginx
    log_info "Nginx restarted"
}

verify_deployment() {
    log_step "Verifying deployment..."
    
    # Check services status
    if systemctl is-active --quiet tunnel-broker.service; then
        log_info "✓ Tunnel broker service is running"
    else
        log_error "✗ Tunnel broker service failed"
        systemctl status tunnel-broker.service
    fi
    
    if systemctl is-active --quiet web-app.service; then
        log_info "✓ Web app service is running"
    else
        log_error "✗ Web app service failed"
        systemctl status web-app.service
    fi
    
    if systemctl is-active --quiet nginx; then
        log_info "✓ Nginx service is running"
    else
        log_error "✗ Nginx service failed"
        systemctl status nginx
    fi
    
    # Test endpoints
    sleep 5
    
    if curl -sf http://localhost:8080/health >/dev/null; then
        log_info "✓ Tunnel broker API responding"
    else
        log_error "✗ Tunnel broker API not responding"
    fi
    
    if curl -sf http://localhost:5000/health >/dev/null 2>&1; then
        log_info "✓ Web app responding"
    else
        log_error "✗ Web app not responding"
    fi
}

show_completion_message() {
    log_step "Deployment completed!"
    
    echo -e "\n${GREEN}🎉 EDGE SERVER successfully deployed!${NC}\n"
    
    echo "Services:"
    echo "  • Tunnel Broker: http://localhost:8080"
    echo "  • Web Application: http://localhost:5000"
    echo "  • Nginx Proxy: http://localhost (redirects to HTTPS)"
    
    echo -e "\nService Management:"
    echo "  • systemctl status tunnel-broker"
    echo "  • systemctl status web-app"
    echo "  • systemctl logs -f tunnel-broker"
    echo "  • systemctl logs -f web-app"
    
    echo -e "\nConfiguration files:"
    echo "  • Application: $SERVER_DIR"
    echo "  • Nginx: /etc/nginx/sites-enabled/tunnel-broker.conf"
    echo "  • Systemd: /etc/systemd/system/tunnel-broker.service"
    echo "  • Logs: $SERVER_DIR/logs/"
    
    if [[ "$DEPLOY_ENV" == "production" ]]; then
        echo -e "\n${YELLOW}Production setup reminders:${NC}"
        echo "  1. Update domain in /etc/nginx/sites-enabled/tunnel-broker.conf"
        echo "  2. Run: certbot --nginx -d your-domain.com"
        echo "  3. Update SECRET_KEY in systemd service"
        echo "  4. Setup database backups"
        echo "  5. Configure monitoring"
    fi
}

cleanup() {
    log_step "Cleaning up..."
    # Remove any temporary files if needed
}

main() {
    log_info "Starting EDGE SERVER deployment (${DEPLOY_ENV})"
    
    check_prerequisites
    create_users
    setup_directories
    install_application
    setup_systemd_services
    setup_nginx
    setup_ssl
    start_services
    verify_deployment
    cleanup
    show_completion_message
}

# Trap errors and cleanup
trap cleanup ERR EXIT

# Run main function
main "$@"