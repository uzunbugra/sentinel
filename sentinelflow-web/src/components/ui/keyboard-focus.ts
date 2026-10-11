// Scope focus rings to the screens that opt in, including shared child controls.
export const keyboardFocusWithin = [
  "[&_a:focus-visible]:ring-2 [&_a:focus-visible]:ring-blue-500",
  "[&_button:focus-visible]:ring-2 [&_button:focus-visible]:ring-blue-500",
  "[&_input:focus-visible]:ring-2 [&_input:focus-visible]:ring-blue-500",
  "[&_select:focus-visible]:ring-2 [&_select:focus-visible]:ring-blue-500",
  "[&_textarea:focus-visible]:ring-2 [&_textarea:focus-visible]:ring-blue-500",
  "[&_[role=button]:focus-visible]:ring-2 [&_[role=button]:focus-visible]:ring-blue-500",
].join(" ")
