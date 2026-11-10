(() => {
    const inputs = document.querySelectorAll('[data-suggest-type]');

    inputs.forEach((input, index) => {
        const list = document.createElement('datalist');
        const listId = `search-suggestions-${index}`;
        list.id = listId;
        input.setAttribute('list', listId);
        input.setAttribute('autocomplete', 'off');
        document.body.appendChild(list);

        const status = document.createElement('span');
        status.className = 'visually-hidden';
        status.setAttribute('aria-live', 'polite');
        input.insertAdjacentElement('afterend', status);

        let timer;
        let controller;
        input.addEventListener('input', () => {
            window.clearTimeout(timer);
            if (controller) controller.abort();
            list.replaceChildren();
            status.textContent = '';

            const query = input.value.trim();
            if (query.length < 2) return;

            timer = window.setTimeout(async () => {
                controller = new AbortController();
                const url = new URL(input.dataset.suggestUrl, window.location.origin);
                url.searchParams.set('type', input.dataset.suggestType);
                url.searchParams.set('q', query);
                if (input.dataset.suggestMetric) {
                    url.searchParams.set('metric', input.dataset.suggestMetric);
                }

                try {
                    const response = await fetch(url, {
                        headers: {'Accept': 'application/json'},
                        signal: controller.signal,
                    });
                    if (!response.ok) {
                        status.textContent = 'Suggestions are unavailable; you can still submit your search.';
                        return;
                    }
                    const data = await response.json();
                    data.results.forEach(result => {
                        const option = document.createElement('option');
                        option.value = result.value;
                        option.label = result.label;
                        list.appendChild(option);
                    });
                } catch (error) {
                    if (error.name !== 'AbortError') {
                        status.textContent = 'Suggestions are unavailable; you can still submit your search.';
                    }
                }
            }, 200);
        });
    });
})();
