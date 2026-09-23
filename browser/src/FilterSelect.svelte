<script>
    export let label = "";
    export let value = "";
    export let options = []; // [{value, label}]
    export let onChange = () => {};

    function handleChange(e) {
        onChange(e.target.value || "");
    }
    function clear() {
        onChange("");
    }
</script>

<div class="selectWrapper">
    <select bind:value on:change={handleChange}>
        <option value="">{value ? `All ${label}s` : label}</option>
        <hr />
        {#each options as opt}
            <option value={opt.value}>{opt.label}</option>
        {/each}
    </select>
    <div>
        <button
            title="Clear Filter"
            class="clearBtn"
            style="visibility:{value ? 'visible' : 'hidden'}"
            on:click={clear}>&times;</button
        >
    </div>
</div>

<style>
    /* Reuse the relevant pieces of your main.svelte CSS */
    .selectWrapper {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 5px;
    }

    select {
        display: block;
        width: 100%;
        padding: 0.3rem 2.25rem 0.3rem 0.75rem;
        font-size: 1rem;
        line-height: 1.5;
        appearance: none;
        background-color: var(--light-background);
        border: 1px solid var(--border-color);
        border-radius: 0.375rem;
        margin: 3px 0;
        float: left;
        background-image: var(--form-select-bg-img);
        background-repeat: no-repeat;
        background-position: right 0.75rem center;
        background-size: 16px 12px;
    }

    .clearBtn {
        background: transparent;
        border: none;
        padding: 2px;
        font-size: 24px;
        cursor: pointer;
    }
</style>
