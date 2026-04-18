//颜色提取
//
//先看trace（从trace中提取）
//
// 【直接提取的情况】 如果trace.marker/trace.line等字段中具有颜色表示 => 从这里面提取
// 【trace+colorscale】 如果trace.marker/trace.line等字段中没有颜色表示，或者这些字段是数组 =>
// - 如果有colorscale,则提取该colorscale
// - 如果无colorscale，但有coloraxis，则从中继承
// 【使用默认值的情况】 如果都没有则意味着应该是plotly自己给的颜色，则从默认颜色循环中继承(这种情况存在吗)
// 理论上后面两种表示都应从calcdata中提取实际颜色

// 从calcdata中提取： node.calcdata后遍历其中的每一项

// 当前的实现好像不适用于所有类别，请你修改下 要使用的类别： （例如有些情况需要在pt.trace字段中获取 有些类别在pt.color字段中获取 有些类别在pt.mcc中获取 好像不是所有的类别都是从pt.t中获取的）



// go的实现不会有颜色
// px的实现
//heatmap/imshow：
    // 提取colorscale: 从calcdata的trace.colorscale(或trace._colorAx.colorscale)，并trace.colorscale（或trace._colorAx.colorscale）下的zmin和zmax（cmin和cmax）
    // 提取最终颜色：①基于提取的colorscale的信息，使用trace.z二维数组进行计算
    // 如果提取失败 则假设为空
//scatter：
    // 提取colorscale: 从calcdata的trace.marker.colorscale(或trace.marker._colorAx.colorscale)，并trace.marker.colorscale（或trace.marker._colorAx.colorscale）下的cmin和cmax
    // 提取最终颜色：①trace.marker直接提取 ②基于提取的colorscale的信息，使用trace.marker中的color字段进行计算 ③使用每一项的mcc属性
    // 如果提取失败 则假设为空
//scatter3d：
    // 同scatter
//sunburst
    // 对除了第一项的每一项，取.color即可
//Pie
    // 对每一项，取.color即可
//Line（实际上是scatter的trace）
    //提取marker的颜色可仿照scatter(如无trace.marker则不用提取)
    //提取trace.line的颜色
        //提取最终颜色：①trace.marker直接提取
//scatterPolar：
    // 同scatter
//scatterMatric
    // 同scatter
//scatterMap
    // 同scatter
//violin
    // 提取最终颜色：①在trace.marker和trace.line和trace.fillcolor和trace.box中直接提取即可
    // 如果提取失败 则假设为空
//area
    // ①在trace.marker和trace.line和trace.fillcolor中直接提取即可
    // 如果提取失败 则假设为空
//bar
    // 提取colorscale: 从calcdata的trace.marker.colorscale(或trace.marker._colorAx.colorscale)，并trace.marker.colorscale（或trace.marker._colorAx.colorscale）下的cmin和cmax
    // 提取最终颜色：①trace.marker直接提取 ②基于提取的colorscale的信息，使用trace.marker中的color字段进行计算 ③使用每一项的mcc属性
    // 如果提取失败 则假设为空
//barpolar
    // 提取colorscale: 从calcdata的trace.marker.colorscale(或trace.marker._colorAx.colorscale)，并trace.marker.colorscale（或trace.marker._colorAx.colorscale）下的cmin和cmax
    // 提取最终颜色：①trace.marker直接提取 ②基于提取的colorscale的信息，使用trace.marker中的color字段进行计算 ③使用每一项的mcc属性
    // 如果提取失败 则假设为空
//box
    // 提取最终颜色：①在trace.marker和trace.line和trace.fillcolor中直接提取即可
    // 如果提取失败 则假设为空
// treemap
    // 对每一项，取.color即可
//funnel
    // ①在trace.marker中直接提取即可
//hist
    // 提取colorscale: 从calcdata的trace.marker.colorscale(或trace.marker._colorAx.colorscale)，并trace.marker.colorscale（或trace.marker._colorAx.colorscale）下的cmin和cmax
    // 提取最终颜色：①trace.marker直接提取 ②基于提取的colorscale的信息，使用trace.marker中的color字段进行计算 ③使用每一项的mcc属性
    // 如果提取失败 则假设为空
//linepolar
    //提取marker的颜色可仿照scatter(如无trace.marker则不用提取)
    //提取trace.line的颜色
        //提取最终颜色：①trace.marker直接提取
//parallel_categories
    // 提取colorscale: 从calcdata的trace.line.colorscale(或trace.marker._colorAx.colorscale)，并trace.line.colorscale（或trace.marker._colorAx.colorscale）下的cmin和cmax
    // 提取最终颜色：①trace.line直接提取 ②基于提取的colorscale的信息，使用trace.line中的color字段进行计算 ③使用每一项的mcc属性
    // 如果提取失败 则假设为空
//parallel_coordinates
    // 提取colorscale: 从calcdata的trace.line.colorscale(或trace.line._colorAx.colorscale)，并trace.line.colorscale（或trace.line._colorAx.colorscale）下的cmin和cmax
    // 提取最终颜色：①trace.line直接提取 ②基于提取的colorscale的信息，使用trace.line中的color字段进行计算 ③使用每一项的mcc属性
    // 如果提取失败 则假设为空

//hex 字符串 #FF00CC
//
//CSS 名称 red, blue
//
//rgb(), rgba(), hsl(), hsla()


/**
 * 将任意 CSS 颜色解析为 [r,g,b,a] 数组
 */
function parseColorCSS(color) {
    const ctx = document.createElement('canvas').getContext('2d');
    ctx.fillStyle = color;
    const computed = ctx.fillStyle;
    ctx.fillStyle = computed;
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], +(d[3] / 255).toFixed(2)];
}

function rgbaString(rgba) {
    if (!rgba) return null;
    const [r,g,b,a] = rgba;
    return `rgba(${r},${g},${b},${a})`;
}

function normalizeColorscale(colorscale, cmin, cmax) {
    if (!Array.isArray(colorscale)) return null;
    const dict = {};
    for (let [pos, col] of colorscale) {
        dict[pos] = rgbaString(parseColorCSS(col));
    }
    return dict;
}

/**
 * colorscale: [[0, color], [1, color], ...]
 * color 可以是任意 CSS 格式
 */
function interpColorscale(val, colorscale, cmin, cmax) {
    if (!Array.isArray(colorscale) || cmin == null || cmax == null) return null;

    const t = (val - cmin) / (cmax - cmin);
    for (let i = 1; i < colorscale.length; i++) {
        const [p0, c0] = colorscale[i - 1];
        const [p1, c1] = colorscale[i];
        if (t >= p0 && t <= p1) {
            const ratio = (t - p0) / (p1 - p0);
            const rgba0 = parseColorCSS(c0);
            const rgba1 = parseColorCSS(c1);
            const rgba = [
                Math.round(rgba0[0] + (rgba1[0] - rgba0[0]) * ratio),
                Math.round(rgba0[1] + (rgba1[1] - rgba0[1]) * ratio),
                Math.round(rgba0[2] + (rgba1[2] - rgba0[2]) * ratio),
                +(rgba0[3] + (rgba1[3] - rgba0[3]) * ratio).toFixed(2)
            ];
            return rgbaString(rgba);
        }
    }
    return null;
}


function parseMaybeColor(value) {
    // 数字 / null / 非 CSS 颜色: 返回 null
    if (typeof value === 'number' || value == null) return null;
    try {
        return rgbaString(parseColorCSS(value));
    } catch {
        return null;
    }
}

function extractHeatmap(calcdata) {
    const t = calcdata[0]?.trace;
    const z = t?.z;
    const colorscale = t.colorscale ?? t._colorAx?.colorscale;
    const cmin = t.zmin ?? t._colorAx?.cmin;
    const cmax = t.zmax ?? t._colorAx?.cmax;

    const mapped = (Array.isArray(z) && colorscale)
        ? z.flat().map(val => interpColorscale(val, colorscale, cmin, cmax))
        : [];

    return {
        "colorscale": {
            "colorscale": normalizeColorscale(colorscale, cmin, cmax),
            "cmin": cmin,
            "cmax": cmax
        },
        "colors": mapped.filter(c => c != null),
    };
}




function extractScatterBar(calcdata) {
    const t = calcdata[0]?.trace ?? {};
    const marker = t.marker ?? {};
    const colorscale = marker.colorscale ?? marker._colorAx?.colorscale;
    const cmin = marker.cmin ?? marker._colorAx?.cmin;
    const cmax = marker.cmax ?? marker._colorAx?.cmax;

    // direct CSS 色
    const directRGBA = [];
    if (marker.color != null) {
        if (Array.isArray(marker.color)) {
            for (const v of marker.color) {
                const col = parseMaybeColor(v);
                if (col) directRGBA.push(col);
            }
        } else {
            const col = parseMaybeColor(marker.color);
            if (col) directRGBA.push(col);
        }
    }

    // mapped (来自数值 => colorscale)
    const mapped = (Array.isArray(marker.color) && colorscale)
        ? marker.color.map(v => interpColorscale(v, colorscale, cmin, cmax))
        : [];

    return {
        "colorscale": {
            "colorscale": normalizeColorscale(colorscale),
            "cmin": cmin,
            "cmax": cmax
        },
        "colors": [...directRGBA, ...mapped].filter(c => c != null)
    };
}


function extractPie_Treemap_Sunburst(calcdata) {
    const colors = calcdata
        .map(c => parseMaybeColor(c.color))
        .filter(c => c != null);
    return {
        "colorscale": { "colorscale": null, "cmin": null, "cmax": null },
        "colors":colors.filter(c => c != null)
    };
}


function extractLine(calcdata) {
    const t = calcdata[0]?.trace ?? {};
    const colors = [];

    if (t.marker) {
        const sb = extractScatterBar(calcdata);
        colors.push(...sb.colors);
    }
    if (t.line?.color) {
        colors.push(rgbaString(parseColorCSS(t.line.color)));
    }

    return {
        "colorscale": { "colorscale": null, "cmin": null, "cmax": null },
        "colors": colors.filter(c => c != null)
    };
}



function extractBasicFill(calcdata) {
    const t = calcdata[0]?.trace ?? {};
    const colors = [];

    const m = parseMaybeColor(t.marker?.color);
    if (m) colors.push(m);

    const l = parseMaybeColor(t.line?.color);
    if (l) colors.push(l);

    const f = parseMaybeColor(t.fillcolor);
    if (f) colors.push(f);

    return {
        "colorscale": { "colorscale": null, "cmin": null, "cmax": null },
        "colors": colors.filter(c => c != null)
    };
}



function extractBox(calcdata) {
    const colors = extractLine(calcdata).colors  //从trace.marker和trace.line中抽取颜色
    const t = calcdata[0]?.trace ?? {};
    const f = parseMaybeColor(t.fillcolor);  //从trace.fillcolor中提取颜色
    if (f) colors.push(f);

    return {
        "colorscale": { "colorscale": null, "cmin": null, "cmax": null },
        "colors": colors.filter(c => c != null)
    };
}


function extractviolin(calcdata) {
    const colors = extractLine(calcdata).colors  //从trace.marker和trace.line中抽取颜色
    const t = calcdata[0]?.trace ?? {};
    const f = parseMaybeColor(t.fillcolor);  //从trace.fillcolor中提取颜色
    if (f) colors.push(f);
    //从trace.box中提取颜色
    if (t.box && t.box.visible === true) {
        colors.push(parseMaybeColor(t.box.fillcolor));  // 提取 box 的颜色
        colors.push(parseMaybeColor(t.box.line?.color ?? null));  // 提取 box 的颜色
    }
    return {
        "colorscale": { "colorscale": null, "cmin": null, "cmax": null },
        "colors": colors.filter(c => c != null)
    };
}




function extractParallel(calcdata) {
    const t = calcdata[0]?.trace ?? {};
    const line = t.line ?? {};
    const colorscale = line.colorscale ?? line._colorAx?.colorscale;
    const cmin = line.cmin ?? line._colorAx?.cmin;
    const cmax = line.cmax ?? line._colorAx?.cmax;

    const directRGBA = [];
    if (line.color != null) {
        if (Array.isArray(line.color)) {
            for (const v of line.color) {
                const col = parseMaybeColor(v);
                if (col) directRGBA.push(col);
            }
        } else {
            const col = parseMaybeColor(line.color);
            if (col) directRGBA.push(col);
        }
    }

    const mapped = Array.isArray(line.color) && colorscale
        ? line.color.map(v => interpColorscale(v, colorscale, cmin, cmax))
        : [];


    return {
        "colorscale": {
            "colorscale": normalizeColorscale(colorscale),
            "cmin": cmin,
            "cmax": cmax
        },
        "colors": [...directRGBA, ...mapped].filter(c => c != null)
    };
}






function extract_All(calcdata_full) {

  // ========== 基于 trace.type 的直接映射 ==========
  const byTraceType = {
    bar: extractScatterBar,
    box: extractBox,
    violin: extractviolin,
    histogram: extractScatterBar,
    funnel: extractScatterBar,

    pie: extractPie_Treemap_Sunburst,
    sunburst: extractPie_Treemap_Sunburst,
    treemap: extractPie_Treemap_Sunburst,

    parcats: extractParallel,
    parcoords: extractParallel,

    scatterpolar: extractScatterBar,
    barpolar: extractScatterBar,
    scatter3d: extractScatterBar,
    splom: extractScatterBar,

    scattermapbox: extractScatterBar,
    scattermap: extractScatterBar,
    scattergeo: extractScatterBar,

    heatmap: extractHeatmap,
    image: extractHeatmap,
  };

  // ========== 针对 trace.type === "scatter" 的二次分流 ==========
  function routeScatterFamily(cd, trace) {
    const fill = trace?.fill;
    const hasAreaFill = fill && fill !== "none" && fill !== false;
    if (hasAreaFill) return extractBasicFill;

    const mode = trace?.mode || "";
    const hasLines = mode.includes("lines");
    const hasMarkers = mode.includes("markers");
    if (hasLines && !hasMarkers) return extractLine;

    return extractScatterBar;
  }

  function isNonEmptyPlainObject(x) {
    return !!x && typeof x === "object" && !Array.isArray(x) && Object.keys(x).length > 0;
  }

  // ========== 主遍历逻辑 ==========
  const results = [];
  const n = calcdata_full?.length ?? 0;

  for (let i = 0; i < n; i++) {
    const cd = calcdata_full[i];
    let out = {};

    try {
      const trace = cd?.trace ?? cd?.[0]?.trace;
      if (!trace) continue;

      const t = trace.type;
      let extractor = byTraceType[t];

      if (!extractor && t === "scatter") {
        extractor = routeScatterFamily(cd, trace);
      }

      if (typeof extractor !== "function") continue;

      const maybeDict = extractor(cd, trace);

      // 只有 extractor 返回“非空字典”才算成功
      if (isNonEmptyPlainObject(maybeDict)) {
        out = { ...maybeDict, trace_type: t }; // ✅ 加上 trace_type（不做二次分流命名）
      } else {
        out = {}; // ✅ 兜底：直接空字典（不保留 trace_type）
      }
    } catch (e) {
      out = {};
    }

    // ✅ results 只返回非空字典
    if (isNonEmptyPlainObject(out)) {
      results.push(out);
    }
  }

  return results;
}