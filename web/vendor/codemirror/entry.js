// The parts of CodeMirror 6 Daf's book editor (web/ebookedit.js) uses, in one file.
export { EditorState, EditorSelection, Compartment, StateEffect, StateField, RangeSetBuilder } from '@codemirror/state';
export { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, dropCursor,
  highlightSpecialChars, rectangularSelection, crosshairCursor, Decoration, ViewPlugin } from '@codemirror/view';
export { defaultKeymap, history, historyKeymap, indentWithTab, undo, redo, undoDepth, redoDepth } from '@codemirror/commands';
export { syntaxHighlighting, HighlightStyle, bracketMatching, foldGutter, indentOnInput, foldKeymap, indentUnit } from '@codemirror/language';
export { highlightSelectionMatches } from '@codemirror/search';
export { closeBrackets, closeBracketsKeymap, autocompletion, completionKeymap } from '@codemirror/autocomplete';
export { html } from '@codemirror/lang-html';
export { css } from '@codemirror/lang-css';
export { xml } from '@codemirror/lang-xml';
export { tags } from '@lezer/highlight';
