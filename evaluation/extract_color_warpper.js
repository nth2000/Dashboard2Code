// 该文件会自动导入extract_color.js中的内容

(function () {

    let debounceTimer = null;

    function collectPlotlyGraphs() {
        const graphNodes = Array.from(
            document.querySelectorAll('.js-plotly-plot')
        );

        const results = graphNodes
            .map(node => {
                const rect = node.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0;

                return {
                    visible: isVisible,
                    x: rect.x + window.scrollX,
                    y: rect.y + window.scrollY,
                    width: rect.width,
                    height: rect.height,
                    figure: {
                        data: node.data,
                        layout: node.layout,
                        colors_extracted: extract_All(node.calcdata)   //TODO：关键修改点在这里
                    }
                };
            })
            .filter(r => r.visible);


        console.log(results.filter(r => r.visible))

        return results.filter(r => r.visible);
    }



    function scheduleCollect() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(collectPlotlyGraphs, 120);
    }

    // 1️⃣ 捕获 Dash / React DOM 更新
    const observer = new MutationObserver(scheduleCollect);
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    // 2️⃣ 捕获 Plotly 自身交互
    document.addEventListener('plotly_afterplot', scheduleCollect);
    document.addEventListener('plotly_relayout', scheduleCollect);
    document.addEventListener('plotly_doubleclick', scheduleCollect);

    // 3️⃣ 首次加载
    window.addEventListener('load', scheduleCollect);

})();