const VERSION = 3;
const SIZE = VERSION * 4 + 17;
const DATA_CODEWORDS = 55;
const EC_CODEWORDS = 15;

function makeGfTables() {
  const exp = new Array(255);
  const log = new Array(256).fill(0);
  let value = 1;
  for (let i = 0; i < 255; i += 1) {
    exp[i] = value;
    log[value] = i;
    value <<= 1;
    if (value & 0x100) value ^= 0x11d;
  }
  return { exp, log };
}

const GF = makeGfTables();

function gfMul(x, y) {
  if (x === 0 || y === 0) return 0;
  return GF.exp[(GF.log[x] + GF.log[y]) % 255];
}

function reedSolomonDivisor(degree) {
  const result = new Array(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i += 1) {
    for (let j = 0; j < degree; j += 1) {
      result[j] = gfMul(result[j], root);
      if (j + 1 < degree) result[j] ^= result[j + 1];
    }
    root = gfMul(root, 2);
  }
  return result;
}

function reedSolomonRemainder(data, degree) {
  const divisor = reedSolomonDivisor(degree);
  const result = new Array(degree).fill(0);
  data.forEach((byte) => {
    const factor = byte ^ result.shift();
    result.push(0);
    for (let i = 0; i < degree; i += 1) {
      result[i] ^= gfMul(divisor[i], factor);
    }
  });
  return result;
}

function appendBits(bits, value, length) {
  for (let i = length - 1; i >= 0; i -= 1) {
    bits.push(((value >>> i) & 1) === 1);
  }
}

function encodeData(text) {
  const bytes = Array.from(unescape(encodeURIComponent(text)), (char) => char.charCodeAt(0));
  if (bytes.length > DATA_CODEWORDS - 2) {
    throw new Error("QR Code 内容过长");
  }
  const bits = [];
  appendBits(bits, 0x4, 4);
  appendBits(bits, bytes.length, 8);
  bytes.forEach((byte) => appendBits(bits, byte, 8));
  appendBits(bits, 0, Math.min(4, DATA_CODEWORDS * 8 - bits.length));
  while (bits.length % 8) bits.push(false);

  const data = [];
  for (let i = 0; i < bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j += 1) byte = (byte << 1) | (bits[i + j] ? 1 : 0);
    data.push(byte);
  }
  for (let pad = 0xec; data.length < DATA_CODEWORDS; pad = pad === 0xec ? 0x11 : 0xec) {
    data.push(pad);
  }
  return data.concat(reedSolomonRemainder(data, EC_CODEWORDS));
}

function makeMatrix() {
  const modules = Array.from({ length: SIZE }, () => new Array(SIZE).fill(false));
  const reserved = Array.from({ length: SIZE }, () => new Array(SIZE).fill(false));
  const setFunction = (x, y, dark) => {
    if (x < 0 || y < 0 || x >= SIZE || y >= SIZE) return;
    modules[y][x] = dark;
    reserved[y][x] = true;
  };

  const drawFinder = (left, top) => {
    for (let y = -1; y <= 7; y += 1) {
      for (let x = -1; x <= 7; x += 1) {
        const xx = left + x;
        const yy = top + y;
        const isCore = x >= 0 && x <= 6 && y >= 0 && y <= 6;
        const dark = isCore && (x === 0 || x === 6 || y === 0 || y === 6 || (x >= 2 && x <= 4 && y >= 2 && y <= 4));
        setFunction(xx, yy, dark);
      }
    }
  };

  drawFinder(0, 0);
  drawFinder(SIZE - 7, 0);
  drawFinder(0, SIZE - 7);

  for (let i = 8; i < SIZE - 8; i += 1) {
    setFunction(i, 6, i % 2 === 0);
    setFunction(6, i, i % 2 === 0);
  }

  const center = 22;
  for (let y = -2; y <= 2; y += 1) {
    for (let x = -2; x <= 2; x += 1) {
      const dark = Math.max(Math.abs(x), Math.abs(y)) !== 1;
      setFunction(center + x, center + y, dark);
    }
  }

  setFunction(8, VERSION * 4 + 9, true);

  for (let i = 0; i <= 8; i += 1) {
    if (i !== 6) {
      setFunction(8, i, false);
      setFunction(i, 8, false);
    }
  }
  for (let i = 0; i < 8; i += 1) {
    setFunction(SIZE - 1 - i, 8, false);
    setFunction(8, SIZE - 1 - i, false);
  }

  return { modules, reserved, setFunction };
}

function formatBits(mask) {
  const data = (1 << 3) | mask;
  let rem = data << 10;
  for (let i = 14; i >= 10; i -= 1) {
    if (((rem >>> i) & 1) !== 0) rem ^= 0x537 << (i - 10);
  }
  return ((data << 10) | rem) ^ 0x5412;
}

function drawFormat(setFunction, mask) {
  const bits = formatBits(mask);
  for (let i = 0; i <= 5; i += 1) setFunction(8, i, ((bits >>> i) & 1) !== 0);
  setFunction(8, 7, ((bits >>> 6) & 1) !== 0);
  setFunction(8, 8, ((bits >>> 7) & 1) !== 0);
  setFunction(7, 8, ((bits >>> 8) & 1) !== 0);
  for (let i = 9; i < 15; i += 1) setFunction(14 - i, 8, ((bits >>> i) & 1) !== 0);
  for (let i = 0; i < 8; i += 1) setFunction(SIZE - 1 - i, 8, ((bits >>> i) & 1) !== 0);
  for (let i = 8; i < 15; i += 1) setFunction(8, SIZE - 15 + i, ((bits >>> i) & 1) !== 0);
}

function makeQrModules(text) {
  const codewords = encodeData(text);
  const { modules, reserved, setFunction } = makeMatrix();
  const bits = [];
  codewords.forEach((byte) => appendBits(bits, byte, 8));

  let bitIndex = 0;
  let upward = true;
  for (let right = SIZE - 1; right >= 1; right -= 2) {
    if (right === 6) right -= 1;
    for (let vert = 0; vert < SIZE; vert += 1) {
      const y = upward ? SIZE - 1 - vert : vert;
      for (let dx = 0; dx < 2; dx += 1) {
        const x = right - dx;
        if (reserved[y][x]) continue;
        const bit = bitIndex < bits.length ? bits[bitIndex] : false;
        const mask = (x + y) % 2 === 0;
        modules[y][x] = bit !== mask;
        bitIndex += 1;
      }
    }
    upward = !upward;
  }
  drawFormat(setFunction, 0);
  return modules;
}

function drawQrCode(page, canvasId, text, rpxSize = 280) {
  const modules = makeQrModules(text);
  const systemInfo = wx.getSystemInfoSync();
  const sizePx = Math.round((rpxSize * systemInfo.windowWidth) / 750);
  const quiet = 4;
  const count = modules.length + quiet * 2;
  const cell = sizePx / count;
  const ctx = wx.createCanvasContext(canvasId, page);
  ctx.setFillStyle("#ffffff");
  ctx.fillRect(0, 0, sizePx, sizePx);
  ctx.setFillStyle("#111111");
  modules.forEach((row, y) => {
    row.forEach((dark, x) => {
      if (dark) {
        ctx.fillRect((x + quiet) * cell, (y + quiet) * cell, Math.ceil(cell), Math.ceil(cell));
      }
    });
  });
  ctx.draw();
}

module.exports = {
  makeQrModules,
  drawQrCode
};
