"use strict";

const archive = window.URPP_ARCHIVE;

function createElement(tag, className, content) {
    const element = document.createElement(tag);

    if (className) {
        element.className = className;
    }

    if (content !== undefined) {
        element.textContent = content;
    }

    return element;
}

function appendText(parent, tag, className, content) {
    const element = createElement(
        tag,
        className,
        content,
    );

    parent.appendChild(element);

    return element;
}

function appendDetails(parent, title, paragraphs, code) {
    const details = createElement("details");

    const summary = createElement(
        "summary",
        "",
        title,
    );

    details.appendChild(summary);

    const body = createElement(
        "div",
        "details-content",
    );

    for (const paragraph of paragraphs) {
        appendText(
            body,
            "p",
            "",
            paragraph,
        );
    }

    if (code) {
        appendText(
            body,
            "pre",
            "",
            code,
        );
    }

    details.appendChild(body);

    parent.appendChild(details);
}

function createCard(title, status, description, metadata) {
    const card = createElement(
        "article",
        "card archive-searchable",
    );

    const header = createElement(
        "div",
        "card-header",
    );

    appendText(
        header,
        "h3",
        "",
        title,
    );

    appendText(
        header,
        "span",
        "badge",
        status,
    );

    card.appendChild(header);

    appendText(
        card,
        "p",
        "",
        description,
    );

    if (metadata) {
        appendText(
            card,
            "p",
            "meta",
            metadata,
        );
    }

    return card;
}

function renderTimeline() {
    const container = document.getElementById(
        "timeline-content"
    );

    for (const record of archive.timeline) {

        const card = createCard(
            record.title,
            record.status,
            record.description,
            `Commit: ${record.commit} · Source: ${record.source}`,
        );

        container.appendChild(card);
    }

    const local = window.URPP_LOCAL_HISTORY;

    if (local && local.commits) {

        const card = createCard(
            "Local Git History Imported",
            "LOCAL SOURCE",
            `${local.commits.length} 个 Commit 已收集。` +
            "完整记录位于 evidence/commit_timeline.txt。" +
            "尚未完成 Implementation 归属审核。",
            `Repository HEAD: ${local.head}`,
        );

        appendDetails(
            card,
            "Show recent local commits",
            local.commits
                .slice(0, 30)
                .map(
                    record =>
                        `${record.hash.slice(0, 10)} — ` +
                        `${record.subject}`
                ),
        );

        container.prepend(card);
    }
}

function renderChapters() {
    const navigation = document.getElementById(
        "chapter-navigation"
    );

    const container = document.getElementById(
        "implementation-content"
    );

    for (const chapter of archive.chapters) {

        const chapterId = String(
            chapter.number
        ).padStart(2, "0");

        const link = createElement(
            "a",
            "",
            `Implementation ${chapterId}`,
        );

        link.href = `#implementation-${chapterId}`;

        navigation.appendChild(link);

        const card = createCard(
            chapter.title,
            "PENDING",
            chapter.description,
            "Original Roadmap mapping required",
        );

        card.id = `implementation-${chapterId}`;

        container.appendChild(card);
    }
}

function renderCasebook() {
    const container = document.getElementById(
        "casebook-content"
    );

    for (const record of archive.cases) {

        const card = createCard(
            record.title,
            record.status,
            record.symptom,
            `${record.id} · ${record.implementation} · ${record.source}`,
        );

        appendDetails(
            card,
            "Full debugging record",
            [
                `Investigation: ${record.investigation}`,
                `Resolution: ${record.resolution}`,
                `Verification: ${record.verification}`,
            ],
            record.error,
        );

        container.appendChild(card);
    }
}

function renderSources() {
    const container = document.getElementById(
        "source-content"
    );

    for (const record of archive.sources) {

        const card = createCard(
            `${record.id} · ${record.title}`,
            "SOURCE",
            record.note,
            `${record.kind} · ${record.locator}`,
        );

        container.appendChild(card);
    }
}

function renderGaps() {
    const container = document.getElementById(
        "gap-content"
    );

    for (const gap of archive.gaps) {

        const card = createCard(
            "Historical evidence required",
            "OPEN",
            gap,
            "",
        );

        container.appendChild(card);
    }
}

function initializeSearch() {
    const input = document.getElementById(
        "global-search"
    );

    const status = document.getElementById(
        "search-status"
    );

    input.addEventListener("input", () => {

        const query = input.value
            .trim()
            .toLocaleLowerCase();

        const cards = Array.from(
            document.querySelectorAll(
                ".archive-searchable"
            )
        );

        let visible = 0;

        for (const card of cards) {

            const matches = card.textContent
                .toLocaleLowerCase()
                .includes(query);

            card.hidden = !matches;

            if (matches) {
                visible += 1;
            }
        }

        status.textContent = query
            ? `Matching records: ${visible}`
            : "Search includes the currently loaded archive.";
    });
}

renderTimeline();

renderChapters();

renderCasebook();

renderSources();

renderGaps();

initializeSearch();
