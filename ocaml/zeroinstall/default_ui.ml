(* Copyright (C) 2013, Thomas Leonard
 * See the README file for details, or visit http://0install.net.
 *)

(** High-level helper functions *)

open General
open Support.Common

let make_ui config distro make_fetcher trust_db use_gui : Ui.ui_handler =
  let use_gui =
    match use_gui, config.dry_run with
    | Yes, true -> raise_safe "Can't use GUI with --dry-run"
    | (Maybe|No), true -> No
    | use_gui, false -> use_gui in

  let make_no_gui () =
    if config.system#isatty Unix.stderr then
      (new Console.console_ui config distro make_fetcher :> Ui.ui_handler)
    else
      (new Console.batch_ui config distro make_fetcher :> Ui.ui_handler) in

  match use_gui with
  | No -> make_no_gui ()
  | Yes | Maybe ->
      (* [try_get_gui] will throw if use_gui is [Yes] and the GUI isn't available *)
      Gui.try_get_gui config distro make_fetcher trust_db ~use_gui |? lazy (make_no_gui ())
