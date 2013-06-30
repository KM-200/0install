open OUnit
open General
open Support.Common

(* let () = Support.Logging.threshold := Support.Logging.Info *)

class fake_system =
  object (_ : #system)
    val now = ref 0.0
    val mutable env = StringMap.empty

    val files = Hashtbl.create 10

    method time () = !now

    method with_open = failwith "file access"
    method mkdir = failwith "file access"
    method readdir = failwith "file access"

    method file_exists path =
      log_info "Check whether file %s exists" path;
      Hashtbl.mem files path

    method lstat = failwith "file access"
    method stat = failwith "file access"
    method atomic_write = failwith "file access"
    method unlink = failwith "file access"

    method exec = failwith "exec"
    method create_process = failwith "exec"
    method reap_child = failwith "reap_child"

    method getcwd = failwith "getcwd"

    method getenv name =
      try Some (StringMap.find name env)
      with Not_found -> None

    method putenv name value =
      env <- StringMap.add name value env
  end
;;

let format_list l = "[" ^ (String.concat "; " l) ^ "]"
let equal_str_lists = assert_equal ~printer:format_list

let test_basedir () =
  let system = new fake_system in
  let open Support.Basedir in

  let bd = get_default_config (system :> system) in
  equal_str_lists ~msg:"No $HOME1" ["/root/.config"; "/etc/xdg"] bd.config;
  equal_str_lists ~msg:"No $HOME2" ["/root/.cache"; "/var/cache"] bd.cache;
  equal_str_lists ~msg:"No $HOME3" ["/root/.local/share"; "/usr/local/share"; "/usr/share"] bd.data;

  system#putenv "HOME" "/home/bob";
  let bd = get_default_config (system :> system) in
  equal_str_lists ~msg:"$HOME1" ["/home/bob/.config"; "/etc/xdg"] bd.config;
  equal_str_lists ~msg:"$HOME2" ["/home/bob/.cache"; "/var/cache"] bd.cache;
  equal_str_lists ~msg:"$HOME3" ["/home/bob/.local/share"; "/usr/local/share"; "/usr/share"] bd.data;

  system#putenv "XDG_CONFIG_HOME" "/home/bob/prefs";
  system#putenv "XDG_CACHE_DIRS" "";
  system#putenv "XDG_DATA_DIRS" "/data1:/data2";
  let bd = get_default_config (system :> system) in
  equal_str_lists ~msg:"XDG1" ["/home/bob/prefs"; "/etc/xdg"] bd.config;
  equal_str_lists ~msg:"XDG2" ["/home/bob/.cache"] bd.cache;
  equal_str_lists ~msg:"XDG3" ["/home/bob/.local/share"; "/data1"; "/data2"] bd.data;

  system#putenv "ZEROINSTALL_PORTABLE_BASE" "/mnt/0install";
  let bd = get_default_config (system :> system) in
  equal_str_lists ~msg:"PORT-1" ["/mnt/0install/config"] bd.config;
  equal_str_lists ~msg:"PORT-2" ["/mnt/0install/cache"] bd.cache;
  equal_str_lists ~msg:"PORT-3" ["/mnt/0install/data"] bd.data;
;; 

let assert_raises_safe expected_msg fn =
  try Lazy.force fn; assert_failure ("Expected Safe_exception " ^ expected_msg)
  with Safe_exception (msg, _) ->
    assert_equal expected_msg msg

let assert_raises_fallback fn =
  try Lazy.force fn; assert_failure "Expected Fallback_to_Python"
  with Fallback_to_Python -> ()

let test_option_parsing () =
  let system = (new fake_system :> system) in
  let config = Config.get_default_config system "/usr/bin/0install" in
  let open Options in
  let p args = Cli.parse_args config args in

  assert_equal Maybe (p []).gui;
  assert_equal No (p ["--console"]).gui;

  let s = p ["--with-store"; "/data/store"; "run"; "foo"] in
  assert_equal "/data/store" (List.hd config.stores);
  equal_str_lists ["run"; "foo"] s.args;

  config.stores <- [];
  let s = p ["--with-store=/data/s1"; "run"; "--with-store=/data/s2"; "foo"; "--with-store=/data/s3"] in
  equal_str_lists ["/data/s2"; "/data/s1"] config.stores;
  equal_str_lists ["run"; "foo"; "--with-store=/data/s3"] s.args;

  assert_raises_safe "Option does not take an argument in '--console=true'" (lazy (p ["--console=true"]));

  let s = p ["-cvv"] in
  assert_equal No s.gui;
  assert_equal 2 s.verbosity;

  let s = p ["run"; "-wgdb"; "foo"] in
  equal_str_lists ["run"; "foo"] s.args;
  assert_equal [("-w", Wrapper "gdb")] s.extra_options;

  assert_raises_fallback (lazy (p ["-c"; "--version"]));

  let s = p ["--version"; "1.2"; "run"; "foo"] in
  equal_str_lists ["run"; "foo"] s.args;
  assert_equal [("--version", RequireVersion "1.2")] s.extra_options;
;;

(* Name the test cases and group them together *)
let suite = 
"0install">:::[
 "test_basedir">:: test_basedir;
 "test_option_parsing">:: test_option_parsing;
];;

let () = Printexc.record_backtrace true;;

let _ = run_test_tt_main suite;;

Format.print_newline ()
