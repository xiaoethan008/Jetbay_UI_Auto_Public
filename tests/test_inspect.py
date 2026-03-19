from pages.base_page import BasePage


def test_inspect_page(page):
    """Inspect page to identify correct selectors for origin/destination inputs."""
    base = BasePage(page)
    base.goto("https://dev.jet-bay.com")
    
    # wait for page to fully load
    page.wait_for_load_state("networkidle")
    
    print("\n=== Page loaded, starting inspection ===")
    print("Now open Developer Tools (F12) in the browser to inspect elements.")
    print("Look for the origin input field and destination input field.")
    print("Note their IDs, class names, or data attributes.")
    
    # pause for manual inspection
    page.pause()
    
    # try to print some debug info
    print("\n=== Attempting to find form inputs ===")
    
    # look for all inputs with placeholder or aria-label containing 'origin', 'from', 'departure'
    inputs = page.query_selector_all("input[type='text']")
    print(f"Found {len(inputs)} text inputs")
    
    for i, inp in enumerate(inputs):
        inp_id = inp.get_attribute("id")
        inp_class = inp.get_attribute("class")
        inp_aria = inp.get_attribute("aria-label")
        inp_placeholder = inp.get_attribute("placeholder")
        print(f"\nInput {i}: id='{inp_id}' aria-label='{inp_aria}' placeholder='{inp_placeholder}'")
    
    # also check for combobox or select patterns
    comboboxes = page.query_selector_all("[role='combobox']")
    print(f"\n=== Found {len(comboboxes)} combobox elements ===")
    for i, cb in enumerate(comboboxes):
        cb_id = cb.get_attribute("id")
        cb_aria = cb.get_attribute("aria-label")
        print(f"Combobox {i}: id='{cb_id}' aria-label='{cb_aria}'")
    
    print("\n✅ Use the above info to update HomePage selectors")
    input("Press enter to finish...")
