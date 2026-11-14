// Shared helpers for inserting text into a multiline widget (wildcard_text)
// at the textarea's caret. No app.registerExtension here: ComfyUI loads every
// .js in this folder as an extension, and this one only exports functions.

// Remember that the user has put the caret in the textarea at least once.
// An untouched textarea may report selectionStart 0, which would insert at
// the very top -- until then we keep the old "append at the end" behavior.
export function track_caret(widget) {
	const el = widget?.inputEl;
	if (!el || el._yoshiaki_caret_tracked) return;
	el._yoshiaki_caret_tracked = true;
	el.addEventListener("focus", () => {
		el._yoshiaki_focused = true;
	});
}

// Insert `text` at the caret (replacing any selection). The caret position
// survives the blur caused by clicking a button / opening a combo menu.
//
// separator (e.g. ", "): when given, it is added before/after `text` only
// where needed so the inserted item stays separated from its neighbours:
//   - before: not at the start, not right after a newline, not after a
//     separator that is already there
//   - after:  not at the end, not right before a newline or a separator
// Falls back to appending (with the separator if the text is non-empty) when
// there is no textarea or it was never focused.
export function insert_at_cursor(widget, text, separator = "") {
	const value = widget.value ?? "";
	const el = widget.inputEl;
	if (!el || !el._yoshiaki_focused) {
		widget.value = value + (separator && value !== "" ? separator : "") + text;
		return;
	}

	const start = Math.min(el.selectionStart ?? value.length, value.length);
	const end = Math.min(el.selectionEnd ?? start, value.length);
	let before = value.slice(0, start);
	const after = value.slice(end);

	let prefix = "";
	let suffix = "";
	if (separator) {
		const sep = separator.trim(); // "," for ", "
		const b = before.trimEnd();
		if (b !== "" && !/\n[ \t]*$/.test(before)) {
			if (sep && b.endsWith(sep)) {
				// "aaa," -> "aaa, x"; "aaa, " stays as is
				prefix = /\s$/.test(before) ? "" : separator.slice(sep.length);
			} else {
				// "aaa" / "aaa " -> "aaa, x"
				before = before.replace(/[ \t]+$/, "");
				prefix = separator;
			}
		}
		const a = after.trimStart();
		if (a !== "" && !/^[ \t]*\n/.test(after) && !(sep && a.startsWith(sep))) {
			// "x bbb" -> "x, bbb"; "xbbb" -> "x, bbb"
			suffix = /^\s/.test(after) ? sep : separator;
		}
	}

	const inserted = prefix + text + suffix;
	widget.value = before + inserted + after;
	// Assigning value moves the caret to the end; put it right after the
	// inserted text so consecutive inserts line up in order.
	const caret = before.length + inserted.length;
	el.setSelectionRange(caret, caret);
}
