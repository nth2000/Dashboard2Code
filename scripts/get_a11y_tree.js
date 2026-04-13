function getSimplifiedTree() {
    var tree = [];
    var idCounter = 0;

    try {
        var allElements = document.querySelectorAll('*');

        function isVisible(el) {
            if (!el) return false;
            var style = window.getComputedStyle(el);
            var rect = el.getBoundingClientRect();

            // 基础检查：尺寸必须大于0
            if (rect.width <= 0 || rect.height <= 0) return false;

            // 检查 display 和 visibility
            if (style.display === 'none' || style.visibility === 'hidden') return false;

            // --- 修正点开始 ---
            // Plotly Parallel Coordinates 的交互层通常是 opacity: 0 但 pointer-events: auto
            var isTransparent = style.opacity === '0';
            var isInteractive = style.pointerEvents !== 'none';
            var classAttr = el.getAttribute('class') || '';

            // 如果是透明的，除非它是特定的交互层，否则过滤掉
            if (isTransparent) {
                // 特例：Plotly 的 axis-brush 背景层
                if (isInteractive && classAttr.indexOf('background') !== -1) {
                    return true;
                }
                return false;
            }
            // --- 修正点结束 ---

            return true;
        }

        for (var i = 0; i < allElements.length; i++) {
            var el = allElements[i];
            if (!isVisible(el)) continue;

            var classAttr = el.getAttribute('class');
            var classNameStr = classAttr ? classAttr.toString() : '';
            var tag = el.tagName.toLowerCase();
            var roleAttr = el.getAttribute('role');
            var detectedRole = null;

            // --- A. 强力降噪区 (Noise Reduction) ---

            // 1. 表格内部降噪 (新增)
            // 忽略 Dash DataTable 和 AgGrid 的具体单元格与表头
            // 我们只需要知道"这里有个表格"，不需要知道每个数据的坐标
            if (classNameStr.indexOf('dash-cell') !== -1 ||
                classNameStr.indexOf('dash-header') !== -1 ||
                classNameStr.indexOf('ag-cell') !== -1 ||
                classNameStr.indexOf('ag-header-cell') !== -1) {
                continue;
            }

            // 2. Plotly/Slider 内部降噪 (原有)
            if (classNameStr.indexOf('modebar') !== -1 ||
                classNameStr.indexOf('rc-slider-tooltip') !== -1 ||
                classNameStr.indexOf('rc-slider-mark') !== -1 ||
                classNameStr.indexOf('rc-slider-rail') !== -1 ||
                classNameStr.indexOf('rc-slider-step') !== -1 ||
                classNameStr.indexOf('rc-slider-dot') !== -1 ||
                classNameStr.indexOf('rc-slider-track') !== -1) {
                continue;
            }

            // 3. Dropdown 内部降噪 (原有)
            if (classNameStr.indexOf('Select-arrow') !== -1 ||
                // classNameStr.indexOf('Select-placeholder') !== -1 ||
                // classNameStr.indexOf('Select-value') !== -1 ||
                // classNameStr.indexOf('Select-clear-zone') !== -1 ||
                classNameStr.indexOf('Select-multi-value-wrapper') !== -1
            ) {
                continue;
            }

            if (tag === 'input' && (classNameStr.indexOf('Select-input') !== -1 || el.getAttribute('aria-activedescendant'))) {
                continue;
            }

            // 4. DAQ 组件降噪 (原有)
            if (classNameStr.indexOf('daq-') !== -1 && classNameStr.indexOf('__') !== -1) {
                continue;
            }

            // --- B. 宏观组件容器 (Macro Components) ---

            // 1. 数据表格容器 (新增核心)
            if (classNameStr.indexOf('dash-table-container') !== -1) {
                detectedRole = 'data_table';
            }
            // 兼容 AgGrid
            else if (classNameStr.indexOf('ag-theme-') !== -1 && classNameStr.indexOf('ag-root-wrapper') !== -1) {
                detectedRole = 'data_table';
            }

            // 2. 图表容器
            else if (classNameStr.indexOf('dash-graph') !== -1) {
                detectedRole = 'chart_container';
            }
            else if (classNameStr.indexOf('js-plotly-plot') !== -1) {
                var parent = el.parentElement;
                var parentClass = (parent && parent.getAttribute('class')) ? parent.getAttribute('class').toString() : '';
                if (parentClass.indexOf('dash-graph') === -1) {
                    detectedRole = 'chart_container';
                } else {
                    continue;
                }
            }

            // 3. 其他容器 (Dropdown, Slider, Tabs...)
            else if (classNameStr.indexOf('dash-dropdown') !== -1) {
                detectedRole = 'dropdown_container';
            }
            else if (classNameStr.indexOf('rc-slider') !== -1 && classNameStr.indexOf('rc-slider-handle') === -1) {
                detectedRole = 'slider_container';
            }
            else if (classNameStr.indexOf('dash-checklist') !== -1 || classNameStr.indexOf('dash-radioitems') !== -1) {
                detectedRole = 'selection_group';
            }
            else if (classNameStr.indexOf('dash-tabs') !== -1) {
                detectedRole = 'tab_group';
            }
            else if (classNameStr.indexOf('daq-') !== -1 && classNameStr.indexOf('daq-uids') === -1) {
                detectedRole = 'daq_component';
            }
            else if (
                classNameStr.indexOf('Select-option') !== -1 ||          // 兼容旧版
                classNameStr.indexOf('react-select__option') !== -1 ||   // 兼容新版标准
                classNameStr.indexOf('VirtualizedSelectOption') !== -1 || // 兼容长列表虚拟化
                (classNameStr.indexOf('-option') !== -1 && classNameStr.indexOf('react-select') !== -1) // 模糊匹配
            ) {
                detectedRole = 'dropdown_option';
            }

            // --- C. 关键交互微元素 (Micro Interactions) ---

            // 2. 轴的交互轨道 (这是 Agent 需要拖拽的目标)
            else if (classNameStr.indexOf('background') !== -1 &&
                     el.parentElement &&
                     el.parentElement.getAttribute('class') === 'axis-brush') {

                detectedRole = 'axis_filter_track'; // 给它一个非常明确的角色
            }

            // 1. 表格分页按钮 (新增 - 特殊处理)
            // 即使是表格的一部分，这些按钮也是必须保留的交互点
            else if (classNameStr.indexOf('next-page') !== -1 ||
                     classNameStr.indexOf('previous-page') !== -1 ||
                     classNameStr.indexOf('first-page') !== -1 ||
                     classNameStr.indexOf('last-page') !== -1) {
                detectedRole = 'button'; // 归类为按钮，方便点击
            }

            // 2. 常规交互元素
            else if (classNameStr.indexOf('Select-control') !== -1) {
                detectedRole = 'dropdown_input';
            }
            else if (classNameStr.indexOf('rc-slider-handle') !== -1) {
                detectedRole = 'slider_handle';
            }
            else if (classNameStr.indexOf('tab') !== -1) {
                detectedRole = 'tab';
            }
            else if (tag === 'input' && (el.type === 'checkbox' || el.type === 'radio')) {
                detectedRole = 'input_option';
            }
            else if (classNameStr.indexOf('form-check-label') !== -1) {
                detectedRole = 'input_label';
            }
            else if (tag === 'button' || roleAttr === 'button') {
                detectedRole = 'button';
            }
            else if (tag === 'input' && classNameStr.indexOf('Select-input') === -1) {
                detectedRole = 'input';
            }
            else if (tag === 'select') {
                detectedRole = 'select';
            }
            else if (tag === 'textarea') {
                detectedRole = 'text_input';
            }
            else if (tag === 'a') {
                detectedRole = 'link';
            }

            else if (classNameStr.indexOf('Select-clear-zone') !== -1) {
                detectedRole = 'clear_all_button';
            }
            else if (classNameStr.indexOf('Select-value-icon') !== -1 ||
                     classNameStr.indexOf('multi-value__remove') !== -1) {
                detectedRole = 'delete_chip'; // 或者 'remove_selection'
            }


            // --- D. 结果收集 ---
            if (detectedRole) {
                var rect = el.getBoundingClientRect();
                // 再次校验尺寸 (Slider handle 除外)
                var isSmall = rect.width < 3 || rect.height < 3;
                if (isSmall && detectedRole !== 'slider_handle') continue;

                tree.push({
                    id: idCounter++,
                    role: detectedRole,
                    tag: tag,
                    box: [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)]
                });
            }
        }
        return tree;

    } catch (e) {
        console.error("DOM Tree extraction error:", e);
        return [];
    }
}
return getSimplifiedTree();