import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox, QLabel,
    QTextEdit, QHeaderView, QFileDialog
)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal
import subprocess
import time
import threading

class ProxyThread(QThread):
    """
    A thread to test a single proxy.
    """
    result = pyqtSignal(dict)

    def __init__(self, proxy):
        super().__init__()
        self.proxy = proxy

    def run(self):
        protocol, ip, port = self.proxy
        start_time = time.time()
        try:
            # We use curl to test the proxy. A timeout is set to 10 seconds.
            # We are trying to access 'http://www.baidu.com' as a test.
            command = f"curl --proxy {protocol.lower()}://{ip}:{port} http://www.baidu.com --silent --output /dev/null --connect-timeout 5"
            subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
            end_time = time.time()
            latency = round((end_time - start_time) * 1000)
            self.result.emit({'proxy': self.proxy, 'latency': latency, 'status': 'Success'})
        except subprocess.CalledProcessError:
            self.result.emit({'proxy': self.proxy, 'latency': -1, 'status': 'Failure'})
        except Exception:
            self.result.emit({'proxy': self.proxy, 'latency': -1, 'status': 'Failure'})


class ProxyPoolApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Arpanet-Proxy-MacOS v1.0')
        self.setGeometry(100, 100, 800, 600)

        self.proxies = []
        self.current_proxy_index = -1
        self.is_service_running = False
        self.auto_switch_timer = QTimer(self)
        self.success_count = 0

        self.initUI()

    def initUI(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Stylesheet ---
        self.setStyleSheet("""
            QMainWindow { background-color: #483D8B; } /* DarkSlateBlue */
            QWidget { background-color: #483D8B; }
            QLabel { color: white; font-size: 14px; }
            QPushButton { 
                font-size: 14px;
                padding: 7px; 
                border-radius: 5px;
                color: black;
                border: 1px solid #6A5ACD;
            }
            QPushButton:hover {
                border: 1px solid #ADD8E6;
            }
            QTableWidget { 
                background-color: #FFFFFF; 
                color: #000000;
                gridline-color: #DCDCDC; /* Gainsboro */
            }
            QHeaderView::section { 
                background-color: #F0F8FF; /* AliceBlue */
                color: black; 
                padding: 4px;
                border: 1px solid #DCDCDC;
            }
            QTextEdit {
                background-color: #F5F5F5; /* WhiteSmoke */
                color: black;
            }
            QComboBox {
                color: black;
                background-color: white;
                padding: 4px;
            }
        """)

        # Top controls
        top_layout = QHBoxLayout()
        self.import_btn = QPushButton('导入代理')
        self.import_btn.setStyleSheet("background-color: #ADD8E6;") # LightBlue
        self.import_btn.clicked.connect(self.import_proxies)
        self.clear_btn = QPushButton('清空代理')
        self.clear_btn.setStyleSheet("background-color: #F08080;") # LightCoral
        self.clear_btn.clicked.connect(self.clear_proxies)
        self.test_btn = QPushButton('测试延迟')
        self.test_btn.setStyleSheet("background-color: #90EE90;") # LightGreen
        self.test_btn.clicked.connect(self.test_all_proxies)
        self.delete_timeout_btn = QPushButton('删除超时')
        self.delete_timeout_btn.setStyleSheet("background-color: #F08080;") # LightCoral
        self.delete_timeout_btn.clicked.connect(self.delete_timed_out_proxies)
        
        top_layout.addWidget(self.import_btn)
        top_layout.addWidget(self.clear_btn)
        top_layout.addWidget(self.test_btn)
        top_layout.addWidget(self.delete_timeout_btn)
        top_layout.addStretch(1)

        main_layout.addLayout(top_layout)

        # Proxy table
        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(4)
        self.proxy_table.setHorizontalHeaderLabels(['协议', '代理地址', '端口', '延迟(ms)'])
        self.proxy_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.proxy_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        main_layout.addWidget(self.proxy_table)

        # Bottom controls
        bottom_layout = QHBoxLayout()
        self.start_service_btn = QPushButton('启动服务')
        self.start_service_btn.setStyleSheet("background-color: #98FB98;") # PaleGreen
        self.start_service_btn.clicked.connect(self.toggle_service)
        
        self.manual_switch_btn = QPushButton('手动切换')
        self.manual_switch_btn.setStyleSheet("background-color: #B0C4DE;") # LightSteelBlue
        self.manual_switch_btn.clicked.connect(self.manual_switch_proxy)
        
        self.auto_switch_combo = QComboBox()
        self.auto_switch_combo.addItems(['自动轮询', '5s', '10s', '20s', '60s', '120s'])
        self.auto_switch_combo.currentIndexChanged.connect(self.setup_auto_switch)

        self.status_label = QLabel('服务状态: 已停止')
        self.success_label = QLabel('成功: 0')

        bottom_layout.addWidget(self.start_service_btn)
        bottom_layout.addWidget(self.manual_switch_btn)
        bottom_layout.addWidget(self.auto_switch_combo)
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addWidget(self.success_label)
        bottom_layout.addStretch(1)
        
        main_layout.addLayout(bottom_layout)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        main_layout.addWidget(self.log_display)

    def log(self, message):
        self.log_display.append(message)

    def import_proxies(self):
        file_names, _ = QFileDialog.getOpenFileNames(self, "选择代理文件", "", "Text Files (*.txt);;All Files (*)")
        if not file_names:
            return
            
        for file_name in file_names:
            try:
                with open(file_name, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Format: protocol://ip:port or ip:port
                        if '://' in line:
                            protocol, address = line.split('://')
                        else:
                            protocol = 'http' # Default protocol
                            address = line

                        ip, port = address.split(':')
                        self.proxies.append((protocol.upper(), ip, port, 'N/A'))
                self.log(f"成功从 {file_name} 导入代理。")
            except Exception as e:
                self.log(f"从 {file_name} 导入代理失败: {e}")
        
        self.update_proxy_table()

    def update_proxy_table(self):
        self.proxy_table.setRowCount(len(self.proxies))
        for i, (protocol, ip, port, latency) in enumerate(self.proxies):
            self.proxy_table.setItem(i, 0, QTableWidgetItem(protocol))
            self.proxy_table.setItem(i, 1, QTableWidgetItem(ip))
            self.proxy_table.setItem(i, 2, QTableWidgetItem(port))
            self.proxy_table.setItem(i, 3, QTableWidgetItem(str(latency)))

    def clear_proxies(self):
        self.proxies = []
        self.update_proxy_table()
        self.log("代理列表已清空。")

    def delete_timed_out_proxies(self):
        original_count = len(self.proxies)
        self.proxies = [p for p in self.proxies if p[3] != '超时']
        removed_count = original_count - len(self.proxies)
        if removed_count > 0:
            self.update_proxy_table()
            self.log(f"成功删除 {removed_count} 个超时代理。")
        else:
            self.log("没有找到超时的代理。")

    def test_all_proxies(self):
        if not self.proxies:
            self.log("代理列表为空，请先导入代理。")
            return

        self.log("开始测试所有代理的延迟...")
        self.threads = []
        self.test_results = []
        
        proxies_to_test = [(p[0], p[1], p[2]) for p in self.proxies]

        for proxy in proxies_to_test:
            thread = ProxyThread(proxy)
            thread.result.connect(self.on_test_finished)
            self.threads.append(thread)
            thread.start()

    def on_test_finished(self, result):
        proxy_to_update = result['proxy']
        latency = result['latency']
        
        for i, p in enumerate(self.proxies):
            if p[0] == proxy_to_update[0] and p[1] == proxy_to_update[1] and p[2] == proxy_to_update[2]:
                if latency != -1:
                    self.proxies[i] = (p[0], p[1], p[2], latency)
                    self.log(f"代理 {p[1]}:{p[2]} 测试成功, 延迟: {latency}ms")
                else:
                    self.proxies[i] = (p[0], p[1], p[2], '超时')
                    self.log(f"代理 {p[1]}:{p[2]} 测试失败 (超时)")
                break
        
        self.update_proxy_table()


    def toggle_service(self):
        self.is_service_running = not self.is_service_running
        if self.is_service_running:
            self.start_service_btn.setText('停止服务')
            self.start_service_btn.setStyleSheet("background-color: #FFA07A;") # LightSalmon
            self.status_label.setText('服务状态: 运行中')
            self.log("代理服务已启动。")
            if not self.proxies:
                self.log("警告: 代理列表为空。")
                return
            # Select the first proxy by default
            if self.current_proxy_index == -1:
                 self.current_proxy_index = 0
            self.set_system_proxy(self.proxies[self.current_proxy_index])
        else:
            self.start_service_btn.setText('启动服务')
            self.start_service_btn.setStyleSheet("background-color: #98FB98;") # PaleGreen
            self.status_label.setText('服务状态: 已停止')
            self.log("代理服务已停止。")
            self.unset_system_proxy()
            if self.auto_switch_timer.isActive():
                self.auto_switch_timer.stop()

    def set_system_proxy(self, proxy):
        protocol, ip, port, _ = proxy
        try:
            # First, disable all proxies to start fresh
            subprocess.run(['networksetup', '-setwebproxystate', 'Wi-Fi', 'off'], check=True)
            subprocess.run(['networksetup', '-setsecurewebproxystate', 'Wi-Fi', 'off'], check=True)
            subprocess.run(['networksetup', '-setsocksfirewallproxystate', 'Wi-Fi', 'off'], check=True)

            # Set bypass domains for all cases
            subprocess.run(['networksetup', '-setproxybypassdomains', 'Wi-Fi', '127.0.0.1', 'localhost'], check=True)

            proto_lower = protocol.lower()
            if proto_lower == 'http' or proto_lower == 'https':
                # Set both web and secure web proxy for HTTP/HTTPS
                subprocess.run(['networksetup', '-setwebproxy', 'Wi-Fi', ip, port], check=True)
                subprocess.run(['networksetup', '-setsecurewebproxy', 'Wi-Fi', ip, port], check=True)
                subprocess.run(['networksetup', '-setwebproxystate', 'Wi-Fi', 'on'], check=True)
                subprocess.run(['networksetup', '-setsecurewebproxystate', 'Wi-Fi', 'on'], check=True)
                self.log(f"HTTP/HTTPS 代理已设置为 {ip}:{port}")
            elif 'socks' in proto_lower:
                # Set SOCKS proxy
                subprocess.run(['networksetup', '-setsocksfirewallproxy', 'Wi-Fi', ip, port], check=True)
                subprocess.run(['networksetup', '-setsocksfirewallproxystate', 'Wi-Fi', 'on'], check=True)
                self.log(f"SOCKS 代理已设置为 {ip}:{port}")
            else:
                self.log(f"不支持的代理协议: {protocol}")
                return

            self.success_count += 1
            self.success_label.setText(f'成功: {self.success_count}')
            self.proxy_table.selectRow(self.current_proxy_index)

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.log(f"设置系统代理失败: {e}")
        except Exception as e:
            self.log(f"发生未知错误: {e}")

    def unset_system_proxy(self):
        try:
            # Turn off all proxy types
            subprocess.run(['networksetup', '-setwebproxystate', 'Wi-Fi', 'off'], check=True)
            subprocess.run(['networksetup', '-setsecurewebproxystate', 'Wi-Fi', 'off'], check=True)
            subprocess.run(['networksetup', '-setsocksfirewallproxystate', 'Wi-Fi', 'off'], check=True)
            self.log("系统全局代理已禁用。")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.log(f"禁用系统代理失败: {e}")

    def manual_switch_proxy(self):
        if not self.is_service_running:
            self.log("请先启动服务。")
            return
        if not self.proxies:
            self.log("代理列表为空。")
            return
        
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        self.set_system_proxy(self.proxies[self.current_proxy_index])

    def setup_auto_switch(self, index):
        if self.auto_switch_timer.isActive():
            self.auto_switch_timer.stop()

        if index == 0: # '自动轮询' means off
            return

        intervals = [5, 10, 20, 60, 120]
        interval_seconds = intervals[index - 1]
        
        self.auto_switch_timer.timeout.connect(self.manual_switch_proxy)
        self.auto_switch_timer.start(interval_seconds * 1000)
        self.log(f"已设置自动切换代理，间隔为 {interval_seconds} 秒。")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ProxyPoolApp()
    ex.show()
    sys.exit(app.exec())
