const path = require('path');
const PptxGenJS = require('pptxgenjs');

// 输出文件固定放在项目 docs 目录，便于培训材料统一归档。
const OUTPUT_PATH = path.resolve(__dirname, '../docs/AI网关大模型调用培训.pptx');

// 全局色板围绕“网关路由”主题设计：深灰负责结构，薄荷绿负责关键路径。
const COLORS = {
  charcoal: '20252B',
  charcoal2: '2B333B',
  mint: '35D0A0',
  mintDark: '139B76',
  mintPale: 'DDF7EE',
  cream: 'F5F2E9',
  paper: 'FFFEFA',
  ink: '182028',
  slate: '53606B',
  line: 'D9DED8',
  white: 'FFFFFF',
  warning: 'F4B860',
  warningPale: 'FFF0D5',
  danger: 'D65A5A',
  blue: '4E7CF0',
  bluePale: 'E8EEFF',
};

// 选用当前渲染环境可识别的中文字体，避免导出 PDF 时出现方框字。
const FONT_HEAD = 'Hiragino Sans GB';
const FONT_BODY = 'Hiragino Sans GB';
const FONT_CODE = 'Arial Unicode MS';
const SLIDE_W = 13.333;
const SLIDE_H = 7.5;

// 每次返回新的阴影对象，避免 PptxGenJS 原地修改共享配置。
function makeShadow(opacity = 0.12) {
  return {
    type: 'outer',
    color: '000000',
    blur: 5,
    offset: 2,
    angle: 135,
    opacity,
  };
}

// 添加内容页统一的章节标识、标题与页码。
function addHeader(pptx, slide, title, section, pageNumber, options = {}) {
  const { dark = false, titleSize = 28 } = options;
  const titleColor = dark ? COLORS.white : COLORS.ink;
  const metaColor = dark ? 'AEB8B2' : COLORS.slate;

  slide.addText(section.toUpperCase(), {
    x: 0.65,
    y: 0.38,
    w: 3.2,
    h: 0.26,
    margin: 0,
    fontFace: FONT_BODY,
    fontSize: 9,
    bold: true,
    charSpacing: 1.8,
    color: COLORS.mint,
  });
  slide.addText(title, {
    x: 0.65,
    y: 0.72,
    w: 11.7,
    h: 0.58,
    margin: 0,
    fontFace: FONT_HEAD,
    fontSize: titleSize,
    bold: true,
    color: titleColor,
    breakLine: false,
    fit: 'shrink',
  });
  slide.addText(String(pageNumber).padStart(2, '0'), {
    x: 12.15,
    y: 0.42,
    w: 0.5,
    h: 0.25,
    margin: 0,
    fontFace: FONT_CODE,
    fontSize: 9,
    align: 'right',
    color: metaColor,
  });
  slide.addShape(pptx.ShapeType.ellipse, {
    x: 12.79,
    y: 0.42,
    w: 0.12,
    h: 0.12,
    fill: { color: COLORS.mint },
    line: { color: COLORS.mint, transparency: 100 },
  });
}

// 添加内容页页脚，保持培训主题和页面边界一致。
function addFooter(slide, pageNumber, dark = false) {
  slide.addText('AI 网关 · 大模型调用培训', {
    x: 0.65,
    y: 7.12,
    w: 3.4,
    h: 0.18,
    margin: 0,
    fontFace: FONT_BODY,
    fontSize: 8,
    color: dark ? '87918C' : '87908B',
  });
  slide.addText(`${pageNumber} / 12`, {
    x: 11.8,
    y: 7.12,
    w: 0.9,
    h: 0.18,
    margin: 0,
    fontFace: FONT_CODE,
    fontSize: 8,
    align: 'right',
    color: dark ? '87918C' : '87908B',
  });
}

// 使用矩形卡片承载短信息，避免文字散落且确保对齐。
function addCard(pptx, slide, options) {
  const {
    x,
    y,
    w,
    h,
    title,
    body,
    eyebrow,
    fill = COLORS.paper,
    titleColor = COLORS.ink,
    bodyColor = COLORS.slate,
    accent = COLORS.mint,
    dark = false,
    titleSize = 17,
    bodySize = 12.5,
    shadow = true,
  } = options;

  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: dark ? '414B53' : COLORS.line, width: 0.8 },
    shadow: shadow ? makeShadow(0.08) : undefined,
  });
  slide.addShape(pptx.ShapeType.rect, {
    x: x + 0.18,
    y: y + 0.18,
    w: 0.08,
    h: Math.max(0.34, h - 0.36),
    fill: { color: accent },
    line: { color: accent, transparency: 100 },
  });
  if (eyebrow) {
    slide.addText(eyebrow, {
      x: x + 0.42,
      y: y + 0.2,
      w: w - 0.64,
      h: 0.22,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 8.5,
      bold: true,
      charSpacing: 1,
      color: accent,
    });
  }
  slide.addText(title, {
    x: x + 0.42,
    y: y + (eyebrow ? 0.48 : 0.25),
    w: w - 0.64,
    h: 0.38,
    margin: 0,
    fontFace: FONT_HEAD,
    fontSize: titleSize,
    bold: true,
    color: titleColor,
    fit: 'shrink',
  });
  slide.addText(body, {
    x: x + 0.42,
    y: y + (eyebrow ? 0.95 : 0.77),
    w: w - 0.64,
    h: h - (eyebrow ? 1.12 : 0.94),
    margin: 0,
    fontFace: FONT_BODY,
    fontSize: bodySize,
    color: bodyColor,
    breakLine: false,
    valign: 'top',
    fit: 'shrink',
  });
}

// 代码面板使用等宽字体和行号感装饰，便于投影时快速定位请求结构。
function addCodePanel(pptx, slide, options) {
  const { x, y, w, h, title, code, fontSize = 11.5, accent = COLORS.mint } = options;
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.08,
    fill: { color: COLORS.charcoal },
    line: { color: '3B454D', width: 0.8 },
    shadow: makeShadow(0.12),
  });
  ['D65A5A', 'F4B860', '35D0A0'].forEach((color, index) => {
    slide.addShape(pptx.ShapeType.ellipse, {
      x: x + 0.22 + index * 0.22,
      y: y + 0.2,
      w: 0.1,
      h: 0.1,
      fill: { color },
      line: { color, transparency: 100 },
    });
  });
  slide.addText(title, {
    x: x + 0.88,
    y: y + 0.14,
    w: w - 1.08,
    h: 0.22,
    margin: 0,
    fontFace: FONT_CODE,
    fontSize: 8.5,
    color: 'AAB5AF',
    align: 'right',
  });
  slide.addShape(pptx.ShapeType.line, {
    x: x + 0.18,
    y: y + 0.48,
    w: w - 0.36,
    h: 0,
    line: { color: '455159', width: 0.6 },
  });
  slide.addText(code, {
    x: x + 0.28,
    y: y + 0.62,
    w: w - 0.56,
    h: h - 0.83,
    margin: 0,
    fontFace: FONT_CODE,
    fontSize,
    color: COLORS.white,
    breakLine: false,
    valign: 'top',
    fit: 'shrink',
  });
  slide.addShape(pptx.ShapeType.rect, {
    x: x + 0.05,
    y: y + 0.58,
    w: 0.05,
    h: h - 0.72,
    fill: { color: accent },
    line: { color: accent, transparency: 100 },
  });
}

// 添加流程节点；数字和标题分层，适合展示网关业务链路。
function addFlowNode(pptx, slide, options) {
  const { x, y, w, h, number, title, body, active = false } = options;
  const fill = active ? COLORS.charcoal : COLORS.paper;
  const titleColor = active ? COLORS.white : COLORS.ink;
  const bodyColor = active ? 'C6D0CB' : COLORS.slate;
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: active ? COLORS.mint : COLORS.line, width: active ? 1.5 : 0.8 },
    shadow: makeShadow(active ? 0.16 : 0.07),
  });
  slide.addShape(pptx.ShapeType.ellipse, {
    x: x + 0.18,
    y: y + 0.18,
    w: 0.42,
    h: 0.42,
    fill: { color: COLORS.mint },
    line: { color: COLORS.mint, transparency: 100 },
  });
  slide.addText(String(number), {
    x: x + 0.18,
    y: y + 0.24,
    w: 0.42,
    h: 0.18,
    margin: 0,
    fontFace: FONT_CODE,
    fontSize: 10,
    bold: true,
    align: 'center',
    color: COLORS.charcoal,
  });
  slide.addText(title, {
    x: x + 0.72,
    y: y + 0.18,
    w: w - 0.9,
    h: 0.34,
    margin: 0,
    fontFace: FONT_HEAD,
    fontSize: 16,
    bold: true,
    color: titleColor,
    fit: 'shrink',
  });
  slide.addText(body, {
    x: x + 0.2,
    y: y + 0.75,
    w: w - 0.4,
    h: h - 0.95,
    margin: 0,
    fontFace: FONT_BODY,
    fontSize: 11.5,
    color: bodyColor,
    align: 'left',
    valign: 'top',
    fit: 'shrink',
  });
}

// 绘制带箭头的连接线，表示请求或配置的流向。
function addArrow(pptx, slide, x, y, w, h = 0, color = COLORS.mint, width = 2) {
  slide.addShape(pptx.ShapeType.line, {
    x,
    y,
    w,
    h,
    line: { color, width, endArrowType: 'triangle' },
  });
}

// 统一为每页写入讲者备注，确保 15 分钟培训有明确节奏。
function addSpeakerNotes(slide, notes) {
  slide.addNotes(notes);
}

// 在浅色内容页创建一致的背景与页头页脚。
function createContentSlide(pptx, title, section, pageNumber, options = {}) {
  const slide = pptx.addSlide();
  slide.background = { color: options.dark ? COLORS.charcoal : COLORS.cream };
  addHeader(pptx, slide, title, section, pageNumber, options);
  addFooter(slide, pageNumber, Boolean(options.dark));
  return slide;
}

// 添加短标签，用于强调命名规则或状态。
function addPill(pptx, slide, text, x, y, w, options = {}) {
  const fill = options.fill || COLORS.mintPale;
  const color = options.color || COLORS.mintDark;
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h: options.h || 0.38,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: options.line || fill, width: 0.6 },
  });
  slide.addText(text, {
    x: x + 0.12,
    y: y + 0.09,
    w: w - 0.24,
    h: (options.h || 0.38) - 0.15,
    margin: 0,
    fontFace: options.code ? FONT_CODE : FONT_BODY,
    fontSize: options.fontSize || 10.5,
    bold: options.bold !== false,
    align: options.align || 'center',
    color,
    fit: 'shrink',
  });
}

// 以“圆点 + 两级文字”绘制检查清单，避免使用 Unicode 项目符号。
function addChecklistItem(pptx, slide, options) {
  const { x, y, w, label, detail, color = COLORS.mint, dark = false } = options;
  slide.addShape(pptx.ShapeType.ellipse, {
    x,
    y: y + 0.06,
    w: 0.15,
    h: 0.15,
    fill: { color },
    line: { color, transparency: 100 },
  });
  slide.addText(label, {
    x: x + 0.26,
    y,
    w: 0.62,
    h: 0.28,
    margin: 0,
    fontFace: FONT_BODY,
    fontSize: 11.5,
    bold: true,
    color: dark ? COLORS.white : COLORS.ink,
  });
  slide.addText(detail, {
    x: x + 0.92,
    y,
    w: w - 0.92,
    h: 0.3,
    margin: 0,
    fontFace: FONT_BODY,
    fontSize: 10.5,
    color: dark ? 'B8C2BD' : COLORS.slate,
    fit: 'shrink',
  });
}

// 绘制附录中的紧凑参数行，三列布局可在一页内保留查阅价值。
function addParameterRow(pptx, slide, options) {
  const { x, y, w, name, required, description, tone = 'neutral' } = options;
  const fill = tone === 'primary' ? COLORS.mintPale : tone === 'advanced' ? COLORS.bluePale : COLORS.paper;
  const accent = tone === 'primary' ? COLORS.mintDark : tone === 'advanced' ? COLORS.blue : COLORS.slate;
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 0.47,
    rectRadius: 0.04,
    fill: { color: fill },
    line: { color: COLORS.line, width: 0.45 },
  });
  slide.addText(name, {
    x: x + 0.12,
    y: y + 0.08,
    w: 1.35,
    h: 0.17,
    margin: 0,
    fontFace: FONT_CODE,
    fontSize: 8.4,
    bold: true,
    color: accent,
    fit: 'shrink',
  });
  slide.addText(required, {
    x: x + 1.48,
    y: y + 0.08,
    w: 0.42,
    h: 0.17,
    margin: 0,
    fontFace: FONT_BODY,
    fontSize: 7.8,
    bold: true,
    align: 'center',
    color: required === '必填' ? COLORS.danger : COLORS.slate,
  });
  slide.addText(description, {
    x: x + 0.12,
    y: y + 0.27,
    w: w - 0.24,
    h: 0.13,
    margin: 0,
    fontFace: FONT_BODY,
    fontSize: 7.6,
    color: COLORS.ink,
    fit: 'shrink',
  });
}

async function buildDeck() {
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'AI 网关项目组';
  pptx.company = 'AI 网关项目组';
  pptx.subject = 'AI 网关大模型申请、管理员配置与 API 调用培训';
  pptx.title = 'AI 网关大模型调用培训';
  pptx.lang = 'zh-CN';
  pptx.theme = {
    headFontFace: FONT_HEAD,
    bodyFontFace: FONT_BODY,
    lang: 'zh-CN',
  };

  // 第 1 页：封面使用深色背景和抽象路由图，建立“请求经过网关”的视觉主线。
  {
    const slide = pptx.addSlide();
    slide.background = { color: COLORS.charcoal };
    slide.addShape(pptx.ShapeType.ellipse, {
      x: 9.35,
      y: -0.7,
      w: 4.7,
      h: 4.7,
      fill: { color: COLORS.mint, transparency: 82 },
      line: { color: COLORS.mint, transparency: 100 },
    });
    slide.addShape(pptx.ShapeType.ellipse, {
      x: 10.42,
      y: 4.68,
      w: 2.2,
      h: 2.2,
      fill: { color: COLORS.blue, transparency: 82 },
      line: { color: COLORS.blue, transparency: 100 },
    });
    slide.addText('AI GATEWAY · TRAINING', {
      x: 0.8,
      y: 0.7,
      w: 4.2,
      h: 0.3,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 10,
      bold: true,
      charSpacing: 2.1,
      color: COLORS.mint,
    });
    slide.addText('AI 网关\n大模型调用培训', {
      x: 0.8,
      y: 1.45,
      w: 7.1,
      h: 1.8,
      margin: 0,
      fontFace: FONT_HEAD,
      fontSize: 37,
      bold: true,
      color: COLORS.white,
      breakLine: false,
      fit: 'shrink',
    });
    slide.addText('从模型申请、管理员配置到 API 调用', {
      x: 0.82,
      y: 3.55,
      w: 6.4,
      h: 0.42,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 18,
      color: 'BCC7C1',
    });
    addPill(pptx, slide, '15 分钟精简版', 0.82, 4.42, 1.75, {
      fill: '2F3B3A',
      line: COLORS.mintDark,
      color: COLORS.mint,
      fontSize: 11,
    });
    addPill(pptx, slide, '用户 + 管理员', 2.77, 4.42, 1.75, {
      fill: '2F3B3A',
      line: '51605A',
      color: COLORS.white,
      fontSize: 11,
    });

    const nodes = [
      { x: 8.0, y: 2.1, label: '申请' },
      { x: 9.75, y: 3.55, label: '配置' },
      { x: 11.45, y: 2.0, label: '调用' },
      { x: 9.65, y: 1.15, label: '网关' },
    ];
    nodes.forEach((node, index) => {
      if (index < nodes.length - 1) {
        addArrow(
          pptx,
          slide,
          node.x + 0.7,
          node.y + 0.35,
          nodes[index + 1].x - node.x - 0.75,
          nodes[index + 1].y - node.y,
          index === 2 ? COLORS.blue : COLORS.mint,
          1.4,
        );
      }
      slide.addShape(pptx.ShapeType.ellipse, {
        x: node.x,
        y: node.y,
        w: 0.82,
        h: 0.82,
        fill: { color: index === 3 ? COLORS.mint : COLORS.charcoal2 },
        line: { color: index === 3 ? COLORS.mint : '66736D', width: 1.1 },
      });
      slide.addText(node.label, {
        x: node.x,
        y: node.y + 0.27,
        w: 0.82,
        h: 0.2,
        margin: 0,
        fontFace: FONT_BODY,
        fontSize: 10.5,
        bold: true,
        align: 'center',
        color: index === 3 ? COLORS.charcoal : COLORS.white,
      });
    });
    slide.addText('01 / 12', {
      x: 11.7,
      y: 6.83,
      w: 0.8,
      h: 0.2,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 9,
      align: 'right',
      color: '7C8882',
    });
    addSpeakerNotes(slide, '开场约 30 秒。说明本次只讲一条完整链路：怎么申请、管理员怎么配置、开发人员怎么调用。');
  }

  // 第 2 页：用五步流程概括端到端链路，后续页面逐步展开。
  {
    const slide = createContentSlide(pptx, '一次调用，经过哪些环节？', '全流程总览', 2);
    const flow = [
      ['企微申请', '提交项目、环境与模型需求'],
      ['管理员配置', '分组 → 渠道 → 令牌'],
      ['令牌下发', '通过钉钉安全交付'],
      ['API 调用', '使用统一网关地址和模型名'],
      ['结果返回', '网关选择可用渠道并转发'],
    ];
    flow.forEach((item, index) => {
      const x = 0.65 + index * 2.53;
      addFlowNode(pptx, slide, {
        x,
        y: 2.05,
        w: 2.12,
        h: 2.75,
        number: index + 1,
        title: item[0],
        body: item[1],
        active: index === 1 || index === 3,
      });
      if (index < flow.length - 1) {
        addArrow(pptx, slide, x + 2.18, 3.38, 0.28, 0, COLORS.mintDark, 1.5);
      }
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 2.0,
      y: 5.4,
      w: 9.35,
      h: 0.82,
      rectRadius: 0.08,
      fill: { color: COLORS.mintPale },
      line: { color: 'B9E7D7', width: 0.8 },
    });
    slide.addText('培训记住两件事：管理员保证“配置正确”，调用方保证“地址、令牌、模型名正确”。', {
      x: 2.35,
      y: 5.65,
      w: 8.65,
      h: 0.28,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 15,
      bold: true,
      align: 'center',
      color: COLORS.mintDark,
    });
    addSpeakerNotes(slide, '约 1 分钟。先给全景，再说明后面三页聚焦管理员配置，最后三页聚焦调用。');
  }

  // 第 3 页：申请流程只保留项目内需要知道的入口与交付结果。
  {
    const slide = createContentSlide(pptx, '第一步：通过企微申请模型', '模型申请', 3);
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 0.72,
      y: 1.72,
      w: 4.1,
      h: 4.5,
      rectRadius: 0.08,
      fill: { color: COLORS.charcoal },
      line: { color: COLORS.charcoal },
      shadow: makeShadow(0.14),
    });
    slide.addText('唯一入口', {
      x: 1.08,
      y: 2.12,
      w: 1.2,
      h: 0.28,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 11,
      bold: true,
      charSpacing: 1,
      color: COLORS.mint,
    });
    slide.addText('企微\n“AI 网关模型申请”流程', {
      x: 1.08,
      y: 2.78,
      w: 3.1,
      h: 1.3,
      margin: 0,
      fontFace: FONT_HEAD,
      fontSize: 25,
      bold: true,
      color: COLORS.white,
      fit: 'shrink',
    });
    slide.addText('本培训不展开企微审批细节。审批完成后，由管理员完成网关配置并下发令牌。', {
      x: 1.08,
      y: 4.58,
      w: 3.05,
      h: 0.92,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 13,
      color: 'C3CCC8',
      fit: 'shrink',
    });
    const steps = [
      ['01', '提交需求', '项目、环境、目标模型与申请人'],
      ['02', '等待审批', '确认资源、权限和使用范围'],
      ['03', '接收令牌', '管理员配置完成后通过钉钉下发'],
    ];
    steps.forEach((item, index) => {
      const y = 1.82 + index * 1.42;
      slide.addShape(pptx.ShapeType.ellipse, {
        x: 5.5,
        y,
        w: 0.62,
        h: 0.62,
        fill: { color: index === 2 ? COLORS.mint : COLORS.paper },
        line: { color: COLORS.mintDark, width: 1.2 },
      });
      slide.addText(item[0], {
        x: 5.5,
        y: y + 0.2,
        w: 0.62,
        h: 0.18,
        margin: 0,
        fontFace: FONT_CODE,
        fontSize: 10,
        bold: true,
        align: 'center',
        color: index === 2 ? COLORS.charcoal : COLORS.mintDark,
      });
      slide.addText(item[1], {
        x: 6.45,
        y: y - 0.02,
        w: 2.1,
        h: 0.32,
        margin: 0,
        fontFace: FONT_HEAD,
        fontSize: 17,
        bold: true,
        color: COLORS.ink,
      });
      slide.addText(item[2], {
        x: 6.45,
        y: y + 0.45,
        w: 4.95,
        h: 0.32,
        margin: 0,
        fontFace: FONT_BODY,
        fontSize: 12,
        color: COLORS.slate,
      });
      if (index < steps.length - 1) {
        slide.addShape(pptx.ShapeType.line, {
          x: 5.81,
          y: y + 0.68,
          w: 0,
          h: 0.74,
          line: { color: 'B7D8CD', width: 1.5, dashType: 'dash' },
        });
      }
    });
    addPill(pptx, slide, '申请人无需进入网关后台操作', 7.15, 5.82, 3.3, {
      fill: COLORS.warningPale,
      line: 'EFCB8B',
      color: '8D5A12',
      fontSize: 11.5,
    });
    addSpeakerNotes(slide, '约 1 分钟。强调申请入口即可，不讲企微表单字段；申请人与管理员的职责从这里分开。');
  }

  // 第 4 页：把分组命名拆成项目和环境两部分，降低管理员记忆成本。
  {
    const slide = createContentSlide(pptx, '管理员配置 ① 分组', '管理员配置', 4);
    slide.addText('进入「分组管理」→ 新建分组', {
      x: 0.72,
      y: 1.55,
      w: 4.8,
      h: 0.35,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 16,
      color: COLORS.slate,
    });
    const parts = [
      { label: '项目', value: 'cs', x: 1.2, color: COLORS.blue, fill: COLORS.bluePale },
      { label: '连接符', value: '-', x: 4.7, color: COLORS.slate, fill: COLORS.paper },
      { label: '环境', value: 'test', x: 7.2, color: COLORS.mintDark, fill: COLORS.mintPale },
    ];
    parts.forEach((part) => {
      slide.addText(part.label, {
        x: part.x,
        y: 2.25,
        w: 2.2,
        h: 0.26,
        margin: 0,
        fontFace: FONT_BODY,
        fontSize: 10,
        bold: true,
        align: 'center',
        color: part.color,
      });
      slide.addShape(pptx.ShapeType.roundRect, {
        x: part.x,
        y: 2.75,
        w: 2.2,
        h: 1.35,
        rectRadius: 0.08,
        fill: { color: part.fill },
        line: { color: part.color, width: 1.2 },
        shadow: makeShadow(0.07),
      });
      slide.addText(part.value, {
        x: part.x,
        y: 3.15,
        w: 2.2,
        h: 0.42,
        margin: 0,
        fontFace: FONT_CODE,
        fontSize: 27,
        bold: true,
        align: 'center',
        color: part.color,
      });
    });
    addArrow(pptx, slide, 3.57, 3.43, 0.88, 0, COLORS.line, 1.2);
    addArrow(pptx, slide, 6.1, 3.43, 0.86, 0, COLORS.line, 1.2);
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 10.05,
      y: 2.35,
      w: 2.35,
      h: 2.15,
      rectRadius: 0.08,
      fill: { color: COLORS.charcoal },
      line: { color: COLORS.charcoal },
      shadow: makeShadow(0.14),
    });
    slide.addText('最终分组名', {
      x: 10.4,
      y: 2.78,
      w: 1.65,
      h: 0.25,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 10,
      align: 'center',
      color: 'BFC9C4',
    });
    slide.addText('cs-test', {
      x: 10.25,
      y: 3.34,
      w: 1.95,
      h: 0.45,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 22,
      bold: true,
      align: 'center',
      color: COLORS.mint,
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 1.1,
      y: 5.15,
      w: 11.2,
      h: 0.95,
      rectRadius: 0.06,
      fill: { color: COLORS.paper },
      line: { color: COLORS.line, width: 0.7 },
    });
    slide.addText('命名规则', {
      x: 1.42,
      y: 5.47,
      w: 1.0,
      h: 0.25,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 11,
      bold: true,
      color: COLORS.mintDark,
    });
    slide.addText('项目-环境', {
      x: 2.55,
      y: 5.39,
      w: 2.15,
      h: 0.34,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 19,
      bold: true,
      color: COLORS.ink,
    });
    slide.addText('统一使用小写，避免同一项目出现多套命名。', {
      x: 5.0,
      y: 5.47,
      w: 5.9,
      h: 0.25,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 12.5,
      color: COLORS.slate,
    });
    addSpeakerNotes(slide, '约 1 分钟。分组只表达项目和环境；后续渠道、模型、令牌都复用这个前缀。');
  }

  // 第 5 页：同时展示渠道字段和模型重定向，突出网关名与上游名的边界。
  {
    const slide = createContentSlide(pptx, '管理员配置 ② 渠道', '管理员配置', 5);
    addCard(pptx, slide, {
      x: 0.72,
      y: 1.55,
      w: 5.25,
      h: 4.88,
      eyebrow: '一个模型对应一个渠道',
      title: '渠道基础信息',
      body: '渠道名称\ncs-test-glm-5.1\n\n渠道内模型名\ncs-test-glm-5.1\n\n其他字段\nbase_url、api_key、环境按提供信息填写',
      bodySize: 13.2,
      accent: COLORS.mint,
    });
    slide.addText('模型重定向', {
      x: 6.55,
      y: 1.65,
      w: 2.2,
      h: 0.32,
      margin: 0,
      fontFace: FONT_HEAD,
      fontSize: 18,
      bold: true,
      color: COLORS.ink,
    });
    slide.addText('当李国刚 / 范亚浩提供的实际模型名不符合网关规则时：', {
      x: 6.55,
      y: 2.08,
      w: 5.6,
      h: 0.36,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 11.5,
      color: COLORS.slate,
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 6.55,
      y: 2.75,
      w: 2.55,
      h: 1.1,
      rectRadius: 0.08,
      fill: { color: COLORS.charcoal },
      line: { color: COLORS.charcoal },
    });
    slide.addText('网关模型名', {
      x: 6.84,
      y: 2.98,
      w: 1.98,
      h: 0.18,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 9,
      align: 'center',
      color: 'B9C4BE',
    });
    slide.addText('cs-test-glm-5.1', {
      x: 6.75,
      y: 3.35,
      w: 2.15,
      h: 0.25,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 12.2,
      bold: true,
      align: 'center',
      color: COLORS.mint,
      fit: 'shrink',
    });
    addArrow(pptx, slide, 9.25, 3.3, 0.72, 0, COLORS.mintDark, 2.2);
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 10.15,
      y: 2.75,
      w: 2.25,
      h: 1.1,
      rectRadius: 0.08,
      fill: { color: COLORS.mintPale },
      line: { color: COLORS.mintDark, width: 1 },
    });
    slide.addText('上游实际模型名', {
      x: 10.38,
      y: 2.98,
      w: 1.78,
      h: 0.18,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 9,
      align: 'center',
      color: COLORS.mintDark,
    });
    slide.addText('glm-5.1', {
      x: 10.38,
      y: 3.35,
      w: 1.78,
      h: 0.25,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 14,
      bold: true,
      align: 'center',
      color: COLORS.ink,
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 6.55,
      y: 4.55,
      w: 5.85,
      h: 1.48,
      rectRadius: 0.08,
      fill: { color: COLORS.warningPale },
      line: { color: 'EEC77D', width: 0.8 },
    });
    slide.addText('最后一步：点击「测试」验证连通性', {
      x: 6.92,
      y: 4.87,
      w: 4.6,
      h: 0.3,
      margin: 0,
      fontFace: FONT_HEAD,
      fontSize: 16,
      bold: true,
      color: '7C5315',
    });
    slide.addText('只有测试通过的渠道，才进入令牌配置和用户交付。', {
      x: 6.92,
      y: 5.4,
      w: 4.8,
      h: 0.26,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 11.5,
      color: '8A6429',
    });
    addSpeakerNotes(slide, '约 2 分钟。强调渠道名和对外模型名必须统一；上游实际名不同就用重定向，用户永远使用网关模型名。');
  }

  // 第 6 页：令牌页面突出“权限边界”，并展示从配置到钉钉交付的闭环。
  {
    const slide = createContentSlide(pptx, '管理员配置 ③ 令牌', '管理员配置', 6);
    slide.addText('一个令牌可以授权一个模型，也可以授权同一项目的多个模型。', {
      x: 0.72,
      y: 1.55,
      w: 7.0,
      h: 0.34,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 15,
      color: COLORS.slate,
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 0.72,
      y: 2.15,
      w: 5.45,
      h: 4.1,
      rectRadius: 0.08,
      fill: { color: COLORS.charcoal },
      line: { color: COLORS.charcoal },
      shadow: makeShadow(0.14),
    });
    slide.addText('TOKEN PROFILE', {
      x: 1.08,
      y: 2.5,
      w: 2.2,
      h: 0.22,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 9,
      bold: true,
      charSpacing: 1.4,
      color: COLORS.mint,
    });
    slide.addText('cs-test-glm-5.1-揭昊', {
      x: 1.08,
      y: 3.0,
      w: 4.3,
      h: 0.5,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 20,
      bold: true,
      color: COLORS.white,
      fit: 'shrink',
    });
    const tokenFields = [
      ['关联分组', 'cs-test'],
      ['模型限制', 'cs-test-glm-5.1'],
      ['额度 / 过期', '按项目实际需求设置'],
    ];
    tokenFields.forEach((field, index) => {
      const y = 3.92 + index * 0.62;
      slide.addText(field[0], {
        x: 1.1,
        y,
        w: 1.0,
        h: 0.22,
        margin: 0,
        fontFace: FONT_BODY,
        fontSize: 10,
        color: '98A49E',
      });
      slide.addText(field[1], {
        x: 2.35,
        y,
        w: 2.9,
        h: 0.22,
        margin: 0,
        fontFace: index < 2 ? FONT_CODE : FONT_BODY,
        fontSize: 11.2,
        bold: true,
        color: index === 0 ? COLORS.mint : COLORS.white,
        fit: 'shrink',
      });
    });
    const tokenSteps = [
      ['1', '选择分组', '关联 cs-test'],
      ['2', '限制模型', '仅开放申请范围'],
      ['3', '设置边界', '额度和过期时间'],
      ['4', '安全下发', '通过钉钉交付'],
    ];
    tokenSteps.forEach((item, index) => {
      const x = 6.75 + (index % 2) * 2.9;
      const y = 2.18 + Math.floor(index / 2) * 1.75;
      addCard(pptx, slide, {
        x,
        y,
        w: 2.55,
        h: 1.42,
        eyebrow: `STEP ${item[0]}`,
        title: item[1],
        body: item[2],
        titleSize: 15,
        bodySize: 10.8,
        accent: index === 3 ? COLORS.warning : COLORS.mint,
      });
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 6.75,
      y: 5.58,
      w: 5.45,
      h: 0.65,
      rectRadius: 0.06,
      fill: { color: COLORS.warningPale },
      line: { color: 'EEC77D', width: 0.7 },
    });
    slide.addText('令牌属于敏感凭据：不得写入代码仓库、群公告或公开文档。', {
      x: 7.05,
      y: 5.8,
      w: 4.85,
      h: 0.22,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 11.3,
      bold: true,
      align: 'center',
      color: '835A1B',
    });
    addSpeakerNotes(slide, '约 1.5 分钟。令牌是项目调用权限的边界。重点讲模型限制、额度、过期时间和安全下发。');
  }

  // 第 7 页：一对多路由图说明扩容后用户仍只使用一个模型名。
  {
    const slide = createContentSlide(pptx, '高负载场景：一个模型名，多条渠道', '负载均衡', 7, { dark: true });
    slide.addText('项目负载压力较大时，可申请多个同版本模型实例；管理员配置多条渠道。', {
      x: 0.72,
      y: 1.48,
      w: 8.2,
      h: 0.35,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 14,
      color: 'B8C4BE',
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 0.9,
      y: 2.55,
      w: 3.0,
      h: 1.65,
      rectRadius: 0.08,
      fill: { color: '2E383F' },
      line: { color: COLORS.mint, width: 1.3 },
    });
    slide.addText('用户始终调用', {
      x: 1.25,
      y: 2.92,
      w: 2.3,
      h: 0.25,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 10,
      align: 'center',
      color: 'AAB6B0',
    });
    slide.addText('cs-test-glm-5.1', {
      x: 1.12,
      y: 3.43,
      w: 2.58,
      h: 0.32,
      margin: 0,
      fontFace: FONT_CODE,
      fontSize: 15,
      bold: true,
      align: 'center',
      color: COLORS.mint,
      fit: 'shrink',
    });
    addArrow(pptx, slide, 4.05, 3.38, 1.05, 0, COLORS.mint, 2.4);
    slide.addShape(pptx.ShapeType.ellipse, {
      x: 5.28,
      y: 2.35,
      w: 2.05,
      h: 2.05,
      fill: { color: COLORS.mint },
      line: { color: '82E8C9', width: 1.2 },
      shadow: makeShadow(0.2),
    });
    slide.addText('AI\n网关', {
      x: 5.65,
      y: 2.87,
      w: 1.32,
      h: 0.92,
      margin: 0,
      fontFace: FONT_HEAD,
      fontSize: 22,
      bold: true,
      align: 'center',
      color: COLORS.charcoal,
    });
    const channels = [
      ['渠道 A', '同版本实例 1'],
      ['渠道 B', '同版本实例 2'],
      ['渠道 C', '同版本实例 3'],
    ];
    channels.forEach((channel, index) => {
      const y = 1.9 + index * 1.28;
      addArrow(pptx, slide, 7.5, 3.35, 1.0, y - 2.92, index === 1 ? COLORS.mint : '74827B', 1.7);
      slide.addShape(pptx.ShapeType.roundRect, {
        x: 8.7,
        y,
        w: 3.55,
        h: 0.98,
        rectRadius: 0.06,
        fill: { color: index === 1 ? '2E443D' : '2A333A' },
        line: { color: index === 1 ? COLORS.mint : '56625C', width: 0.9 },
      });
      slide.addText(channel[0], {
        x: 9.02,
        y: y + 0.18,
        w: 0.9,
        h: 0.2,
        margin: 0,
        fontFace: FONT_BODY,
        fontSize: 11,
        bold: true,
        color: index === 1 ? COLORS.mint : COLORS.white,
      });
      slide.addText(channel[1], {
        x: 10.05,
        y: y + 0.18,
        w: 1.78,
        h: 0.2,
        margin: 0,
        fontFace: FONT_BODY,
        fontSize: 10.5,
        align: 'right',
        color: 'AAB6B0',
      });
      slide.addText('上游实际模型名可分别重定向', {
        x: 9.02,
        y: y + 0.55,
        w: 2.82,
        h: 0.18,
        margin: 0,
        fontFace: FONT_BODY,
        fontSize: 9,
        color: '8E9A94',
      });
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 1.75,
      y: 5.65,
      w: 9.85,
      h: 0.72,
      rectRadius: 0.06,
      fill: { color: '27312F' },
      line: { color: '47544E', width: 0.7 },
    });
    slide.addText('用户无感知：地址、令牌、模型名都不变；扩容与渠道维护由管理员完成。', {
      x: 2.05,
      y: 5.91,
      w: 9.25,
      h: 0.24,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 14,
      bold: true,
      align: 'center',
      color: COLORS.white,
    });
    addSpeakerNotes(slide, '约 1 分钟。只承诺用户无感知，不展开权重和调度算法。强调多个实例必须是同版本模型。');
  }

  // 第 8 页：按能力类型整理项目当前已实现路由，避免把未实现接口写入培训范围。
  {
    const slide = createContentSlide(pptx, '网关当前提供哪些接口？', '接口能力地图', 8);
    const endpointCards = [
      {
        x: 0.72,
        y: 1.55,
        w: 3.75,
        h: 2.05,
        title: '模型查询',
        body: 'GET /v1/models\nGET /v1/models/{model}',
        accent: COLORS.blue,
      },
      {
        x: 4.78,
        y: 1.55,
        w: 3.75,
        h: 2.05,
        title: '文本与对话',
        body: 'POST /v1/chat/completions\nPOST /v1/completions\nPOST /v1/responses\nPOST /v1/messages',
        accent: COLORS.mint,
      },
      {
        x: 8.84,
        y: 1.55,
        w: 3.75,
        h: 2.05,
        title: '向量与排序',
        body: 'POST /v1/embeddings\nPOST /v1/rerank',
        accent: COLORS.warning,
      },
      {
        x: 0.72,
        y: 3.95,
        w: 5.85,
        h: 2.2,
        title: '图像与音频',
        body: '图像：/v1/images/generations、/v1/images/edits、/v1/edits\n音频：/v1/audio/transcriptions、/translations、/speech',
        accent: COLORS.danger,
      },
      {
        x: 6.88,
        y: 3.95,
        w: 5.71,
        h: 2.2,
        title: '兼容接口',
        body: '内容审核：POST /v1/moderations\nGemini：/v1beta/models/...\nRealtime：GET /v1/realtime（WebSocket）',
        accent: COLORS.blue,
      },
    ];
    endpointCards.forEach((card) => {
      addCard(pptx, slide, {
        ...card,
        bodySize: 11.2,
        titleSize: 17,
      });
    });
    addPill(pptx, slide, '文件、微调、图片变体等路由当前明确标记为未实现', 3.45, 6.43, 6.45, {
      fill: COLORS.warningPale,
      line: 'EEC77D',
      color: '845715',
      fontSize: 10.8,
    });
    addSpeakerNotes(slide, '约 1.5 分钟。接口地图只做快速认知。培训重点仍是 chat/completions；其他接口按模型能力和申请范围使用。');
  }

  // 第 9 页：左侧展示请求骨架，右侧按用途归纳核心参数。
  {
    const slide = createContentSlide(pptx, '/v1/chat/completions：核心参数', '核心接口', 9);
    addCodePanel(pptx, slide, {
      x: 0.72,
      y: 1.55,
      w: 5.35,
      h: 4.95,
      title: 'request.json',
      fontSize: 11.4,
      code: `{
  "model": "cs-test-glm-5.1",
  "messages": [
    {"role": "system", "content": "你是助手"},
    {"role": "user", "content": "请介绍 AI 网关"}
  ],
  "temperature": 0.3,
  "max_tokens": 512,
  "stream": false
}`,
    });
    const groups = [
      ['必填', 'model', '网关模型名'],
      ['必填', 'messages', '上下文消息数组'],
      ['输出方式', 'stream / stream_options', '流式输出及用量信息'],
      ['输出长度', 'max_tokens / max_completion_tokens', '限制最大生成长度'],
      ['采样', 'temperature / top_p / top_k', '控制随机性与候选范围'],
      ['高级能力', 'tools / tool_choice / response_format', '工具调用与结构化输出'],
    ];
    groups.forEach((group, index) => {
      const x = 6.42 + (index % 2) * 3.1;
      const y = 1.55 + Math.floor(index / 2) * 1.55;
      addCard(pptx, slide, {
        x,
        y,
        w: 2.82,
        h: 1.3,
        eyebrow: group[0],
        title: group[1],
        body: group[2],
        titleSize: 12.8,
        bodySize: 9.8,
        accent: index < 2 ? COLORS.mint : index === 5 ? COLORS.blue : COLORS.warning,
        shadow: false,
      });
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 6.42,
      y: 6.3,
      w: 5.92,
      h: 0.48,
      rectRadius: 0.05,
      fill: { color: COLORS.warningPale },
      line: { color: 'EEC77D', width: 0.7 },
    });
    slide.addText('高级参数是否生效取决于所申请的上游模型，请按实际模型验证。', {
      x: 6.7,
      y: 6.45,
      w: 5.36,
      h: 0.18,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 10.5,
      bold: true,
      align: 'center',
      color: '805615',
    });
    addSpeakerNotes(slide, '约 2 分钟。先讲 model 和 messages，再讲 stream、输出长度和采样。tools 与 response_format 只做能力提示。');
  }

  // 第 10 页：把可复制的 curl、响应读取方式和故障检查放在同一页。
  {
    const slide = createContentSlide(pptx, '从请求到结果：调用示例与检查清单', '快速上手', 10);
    addCodePanel(pptx, slide, {
      x: 0.72,
      y: 1.52,
      w: 7.05,
      h: 4.1,
      title: 'curl',
      fontSize: 10.3,
      code: `curl -X POST '<AI_GATEWAY_BASE_URL>/v1/chat/completions' \\
  -H 'Authorization: Bearer <YOUR_TOKEN>' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "model": "cs-test-glm-5.1",
    "messages": [
      {"role": "user", "content": "请用一句话介绍 AI 网关"}
    ],
    "temperature": 0.3,
    "stream": false
  }'`,
    });
    addCard(pptx, slide, {
      x: 8.1,
      y: 1.52,
      w: 4.5,
      h: 2.05,
      eyebrow: '非流式响应',
      title: '读取 choices[0].message.content',
      body: '同时关注 usage 中的输入、输出和总 token 数。',
      titleSize: 14.3,
      bodySize: 11.2,
      accent: COLORS.mint,
    });
    addCard(pptx, slide, {
      x: 8.1,
      y: 3.82,
      w: 4.5,
      h: 1.8,
      eyebrow: '流式响应',
      title: 'stream: true',
      body: '按 SSE 的 data: 分片读取增量内容，直到 [DONE]。',
      titleSize: 15,
      bodySize: 10.8,
      accent: COLORS.blue,
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 0.72,
      y: 5.92,
      w: 11.88,
      h: 0.73,
      rectRadius: 0.06,
      fill: { color: COLORS.paper },
      line: { color: COLORS.line, width: 0.7 },
    });
    const checks = [
      ['地址', '含 /v1'],
      ['令牌', 'Bearer 格式'],
      ['模型名', '完全一致'],
      ['权限', '分组与模型限制'],
      ['渠道', '启用且测试通过'],
    ];
    checks.forEach((check, index) => {
      addChecklistItem(pptx, slide, {
        x: 1.02 + index * 2.25,
        y: 6.17,
        w: 2.05,
        label: check[0],
        detail: check[1],
        color: index === 4 ? COLORS.warning : COLORS.mint,
      });
    });
    addSpeakerNotes(slide, '约 2 分钟。现场可复制 curl。出错时按照地址、令牌、模型名、权限、渠道状态的顺序排查。');
  }

  // 第 11 页：把 Chat Completions 通用字段按基础、生成控制和高级能力分三列展示。
  {
    const slide = createContentSlide(pptx, '附录：Chat Completions 参数速查', '附录 A', 11, { titleSize: 26 });
    const columns = [
      {
        title: '基础与输出',
        tone: 'primary',
        items: [
          ['model', '必填', '网关模型名'],
          ['messages', '必填*', '消息数组；FIM 场景可用 prefix/suffix'],
          ['stream', '可选', '是否使用 SSE 流式输出'],
          ['stream_options', '可选', '例如 include_usage'],
          ['max_tokens', '可选', '最大输出 token 数'],
          ['max_completion_tokens', '可选', '新式最大输出长度字段'],
          ['n', '可选', '生成候选数量'],
          ['stop', '可选', '遇到字符串或数组中的序列停止'],
          ['user', '可选', '调用方用户标识'],
        ],
      },
      {
        title: '采样与概率',
        tone: 'neutral',
        items: [
          ['temperature', '可选', '控制随机性；越低越稳定'],
          ['top_p', '可选', '核采样候选概率范围'],
          ['top_k', '可选', '限制候选 token 数量'],
          ['frequency_penalty', '可选', '降低高频内容重复'],
          ['presence_penalty', '可选', '鼓励引入新内容'],
          ['seed', '可选', '固定随机种子；效果依模型而定'],
          ['logprobs', '可选', '返回 token 对数概率'],
          ['top_logprobs', '可选', '返回最可能 token 的概率'],
          ['logit_bias', '可选', '调整指定 token 的生成倾向'],
        ],
      },
      {
        title: '工具与高级能力',
        tone: 'advanced',
        items: [
          ['tools', '可选', '声明可调用工具或函数'],
          ['tool_choice', '可选', '控制是否及如何选择工具'],
          ['parallel_tool_calls', '可选', '允许并行工具调用'],
          ['response_format', '可选', 'JSON object / JSON schema 输出'],
          ['reasoning_effort', '可选', '控制推理强度'],
          ['verbosity', '可选', '控制回答详略（特定模型）'],
          ['modalities', '可选', '请求文本、音频等输出模态'],
          ['audio', '可选', '音频输出配置'],
          ['web_search_options', '可选', '网页搜索配置（模型相关）'],
        ],
      },
    ];
    columns.forEach((column, columnIndex) => {
      const x = 0.66 + columnIndex * 4.18;
      const accent = column.tone === 'primary' ? COLORS.mintDark : column.tone === 'advanced' ? COLORS.blue : COLORS.slate;
      slide.addText(column.title, {
        x,
        y: 1.42,
        w: 3.9,
        h: 0.28,
        margin: 0,
        fontFace: FONT_HEAD,
        fontSize: 14,
        bold: true,
        color: accent,
      });
      column.items.forEach((item, rowIndex) => {
        addParameterRow(pptx, slide, {
          x,
          y: 1.82 + rowIndex * 0.5,
          w: 3.9,
          name: item[0],
          required: item[1],
          description: item[2],
          tone: column.tone,
        });
      });
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 0.66,
      y: 6.5,
      w: 12.0,
      h: 0.37,
      rectRadius: 0.04,
      fill: { color: COLORS.warningPale },
      line: { color: 'EEC77D', width: 0.55 },
    });
    slide.addText('兼容性提示：网关能够接收参数，不代表所有上游模型都以相同方式支持；厂商特有扩展参数请结合所申请模型验证。', {
      x: 0.9,
      y: 6.61,
      w: 11.5,
      h: 0.14,
      margin: 0,
      fontFace: FONT_BODY,
      fontSize: 8.5,
      bold: true,
      align: 'center',
      color: '815817',
    });
    addSpeakerNotes(slide, '附录页不逐项讲解。说明必填星号：普通 Chat Completions 需要 messages；FIM 可使用 prefix/suffix。');
  }

  // 第 12 页：按场景列出其余已实现接口，作为会后速查表。
  {
    const slide = createContentSlide(pptx, '附录：其他接口速查', '附录 B', 12, { titleSize: 26 });
    const groups = [
      {
        title: '模型与文本',
        accent: COLORS.mint,
        x: 0.72,
        y: 1.48,
        w: 5.95,
        h: 2.35,
        rows: [
          ['GET', '/v1/models', '查询令牌可访问模型'],
          ['GET', '/v1/models/{model}', '查询单个模型信息'],
          ['POST', '/v1/completions', '传统文本补全'],
          ['POST', '/v1/responses', '统一 Responses 接口'],
          ['POST', '/v1/messages', 'Claude Messages 兼容接口'],
        ],
      },
      {
        title: '向量、排序与审核',
        accent: COLORS.warning,
        x: 6.98,
        y: 1.48,
        w: 5.63,
        h: 2.35,
        rows: [
          ['POST', '/v1/embeddings', '生成向量表示'],
          ['POST', '/v1/rerank', '对候选文本重排'],
          ['POST', '/v1/moderations', '内容审核'],
          ['GET', '/v1/realtime', '实时 WebSocket 接口'],
        ],
      },
      {
        title: '图像',
        accent: COLORS.danger,
        x: 0.72,
        y: 4.08,
        w: 5.95,
        h: 2.3,
        rows: [
          ['POST', '/v1/images/generations', '文本生成图像'],
          ['POST', '/v1/images/edits', '编辑图像'],
          ['POST', '/v1/edits', '兼容编辑入口'],
          ['POST', '/v1beta/models/...', 'Gemini 原生生成接口'],
        ],
      },
      {
        title: '音频',
        accent: COLORS.blue,
        x: 6.98,
        y: 4.08,
        w: 5.63,
        h: 2.3,
        rows: [
          ['POST', '/v1/audio/transcriptions', '语音转文字'],
          ['POST', '/v1/audio/translations', '音频翻译'],
          ['POST', '/v1/audio/speech', '文字转语音'],
          ['POST', '/v1/engines/{model}/embeddings', 'Gemini 兼容向量接口'],
        ],
      },
    ];
    groups.forEach((group) => {
      slide.addShape(pptx.ShapeType.roundRect, {
        x: group.x,
        y: group.y,
        w: group.w,
        h: group.h,
        rectRadius: 0.06,
        fill: { color: COLORS.paper },
        line: { color: COLORS.line, width: 0.7 },
        shadow: makeShadow(0.06),
      });
      slide.addShape(pptx.ShapeType.rect, {
        x: group.x + 0.2,
        y: group.y + 0.2,
        w: 0.08,
        h: group.h - 0.4,
        fill: { color: group.accent },
        line: { color: group.accent, transparency: 100 },
      });
      slide.addText(group.title, {
        x: group.x + 0.42,
        y: group.y + 0.22,
        w: group.w - 0.68,
        h: 0.28,
        margin: 0,
        fontFace: FONT_HEAD,
        fontSize: 14,
        bold: true,
        color: COLORS.ink,
      });
      group.rows.forEach((row, index) => {
        const y = group.y + 0.7 + index * 0.34;
        addPill(pptx, slide, row[0], group.x + 0.42, y, 0.63, {
          h: 0.26,
          fill: group.accent,
          line: group.accent,
          color: group.accent === COLORS.warning ? COLORS.charcoal : COLORS.white,
          code: true,
          fontSize: 7.2,
        });
        slide.addText(row[1], {
          x: group.x + 1.18,
          y: y + 0.03,
          w: 2.92,
          h: 0.16,
          margin: 0,
          fontFace: FONT_CODE,
          fontSize: 8.2,
          bold: true,
          color: COLORS.ink,
          fit: 'shrink',
        });
        slide.addText(row[2], {
          x: group.x + 4.15,
          y: y + 0.03,
          w: group.w - 4.45,
          h: 0.16,
          margin: 0,
          fontFace: FONT_BODY,
          fontSize: 8.2,
          align: 'right',
          color: COLORS.slate,
          fit: 'shrink',
        });
      });
    });
    addPill(pptx, slide, '具体接口能否调用，还取决于令牌模型限制和所申请模型的实际能力', 3.35, 6.48, 6.65, {
      fill: COLORS.mintPale,
      line: 'B8E5D5',
      color: COLORS.mintDark,
      fontSize: 10,
    });
    addSpeakerNotes(slide, '结束页。提醒参训人员：接口存在、令牌授权、上游模型支持三者缺一不可。');
  }

  await pptx.writeFile({ fileName: OUTPUT_PATH });
  console.log(`PPT 已生成：${OUTPUT_PATH}`);
}

// 顶层捕获生成异常，确保自动化执行时返回非零退出码。
buildDeck().catch((error) => {
  console.error('生成 PPT 失败：', error);
  process.exitCode = 1;
});
