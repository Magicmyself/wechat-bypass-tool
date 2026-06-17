import uiautomation as uia

def search_tree():
    print("Getting Root Control...")
    root = uia.GetRootControl()
    
    print("Searching for WeChat related controls in the global UIA tree...")
    found_controls = []
    
    # We will walk all direct children of the root control
    children = root.GetChildren()
    print(f"Root has {len(children)} direct children.")
    
    for idx, child in enumerate(children):
        try:
            name = child.Name
            classname = child.ClassName
            control_type = child.ControlTypeName
            
            is_match = False
            if name and ("微信" in name or "weixin" in name.lower() or "小庄" in name):
                is_match = True
            if classname and ("qt" in classname.lower() or "mmui" in classname.lower()):
                is_match = True
                
            if is_match:
                print(f"Match [{idx}]: Name={repr(name)}, ClassName={repr(classname)}, Type={control_type}, HWND={child.Handle}")
                found_controls.append(child)
        except Exception as e:
            pass
            
    if not found_controls:
        print("No matches found in direct children of root. Searching deeper...")
        # Search recursively for any element containing "mmui::MainWindow" or "Qt51514QWindowIcon"
        def search_recursive(control, depth=0):
            if depth > 3:
                return
            try:
                for c in control.GetChildren():
                    name = c.Name
                    classname = c.ClassName
                    if classname and "mmui::MainWindow" in classname:
                        print(f"Deep match: Name={repr(name)}, ClassName={repr(classname)}, HWND={c.Handle}")
                    search_recursive(c, depth + 1)
            except Exception:
                pass
        search_recursive(root)
        
    # Let's inspect the found controls
    for ctrl in found_controls:
        print(f"\nWalking control: Name={repr(ctrl.Name)}, ClassName={repr(ctrl.ClassName)}")
        try:
            # Check if it has children
            sub = ctrl.GetChildren()
            print(f"Direct children count: {len(sub)}")
            for sidx, s in enumerate(sub[:10]):
                print(f"  [{sidx}] Name={repr(s.Name)}, Class={repr(s.ClassName)}, Type={s.ControlTypeName}")
                # Try one more level
                gsub = s.GetChildren()
                if gsub:
                    print(f"    Grandchildren count: {len(gsub)}")
                    for gidx, gs in enumerate(gsub[:5]):
                        print(f"      [{gidx}] Name={repr(gs.Name)}, Class={repr(gs.ClassName)}, Type={gs.ControlTypeName}")
        except Exception as e:
            print(f"  Error walking control: {e}")

if __name__ == '__main__':
    search_tree()
