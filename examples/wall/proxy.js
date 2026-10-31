// WebSocket <-> VNC TCP 桥，等价于 websockify 的最小实现
// 6081 -> 5911 (Kali) | 6082 -> 5910 (Win7) | 6083 -> 5912 (DC-1)
const { WebSocketServer } = require('ws');
const net = require('net');

const MAP = [
  { ws: 6081, tcp: 5911, name: 'kali' },
  { ws: 6082, tcp: 5910, name: 'win7' },
  { ws: 6083, tcp: 5912, name: 'dc1' },
];

for (const m of MAP) {
  const wss = new WebSocketServer({
    port: m.ws,
    handleProtocols: (protocols) => (protocols.has('binary') ? 'binary' : false),
    perMessageDeflate: false,
  });

  wss.on('connection', (ws) => {
    const tcp = net.connect(m.tcp, '127.0.0.1');
    tcp.setNoDelay(true);
    ws.binaryType = 'nodebuffer';

    tcp.on('data', (buf) => {
      if (ws.readyState === ws.OPEN) ws.send(buf);
    });
    ws.on('message', (data) => {
      if (!tcp.destroyed) tcp.write(data);
    });
    ws.on('close', () => tcp.destroy());
    ws.on('error', () => tcp.destroy());
    tcp.on('close', () => { try { ws.close(); } catch (e) {} });
    tcp.on('error', () => { try { ws.close(); } catch (e) {} });
  });

  console.log(`${m.name}: ws://127.0.0.1:${m.ws} -> tcp://127.0.0.1:${m.tcp}`);
}
