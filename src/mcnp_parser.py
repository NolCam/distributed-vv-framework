import re
import pandas as pd

def parse_mcnp_tallies_to_df(filepath):
    all_tally_results_list = []
    active_tally_data = {
        "number": None,
        "energy_bins": [],
        "results_pairs": []
    }
    in_et_section = False
    in_vals_section = False

    float_regex = re.compile(r"[+\-]?\d*\.\d+(?:[Ee][+\-]?\d+)?|[+\-]?\d+\.\d*(?:[Ee][+\-]?\d+)?|[+\-]?\d+(?:[Ee][+\-]?\d+)?")

    def flush_active_tally_to_list():
        nonlocal all_tally_results_list, active_tally_data
        # print(f"DEBUG: Attempting to flush tally: {active_tally_data['number']}, Results count: {len(active_tally_data['results_pairs'])}, Bins count: {len(active_tally_data['energy_bins'])}")
        if active_tally_data["number"] and active_tally_data["results_pairs"]:
            num_energy_boundaries = len(active_tally_data["energy_bins"])
            
            if not active_tally_data["energy_bins"]: # Case for F1-like tallies with no ET
                for val, err in active_tally_data["results_pairs"]:
                    all_tally_results_list.append({
                        "tally_number": active_tally_data["number"], "energy_bin_idx": -1,
                        "energy_bin_min": None, "energy_bin_max": None,
                        "value": val, "relative_error": err
                    })
            else: # Case for tallies with ET an VALS
                num_expected_bins = num_energy_boundaries - 1 if num_energy_boundaries > 0 else 0
                for i, (val, err) in enumerate(active_tally_data["results_pairs"]):
                    if i < num_expected_bins :
                        if i + 1 < num_energy_boundaries: # Ensure we have a pair for bin max
                            all_tally_results_list.append({
                                "tally_number": active_tally_data["number"], "energy_bin_idx": i,
                                "energy_bin_min": active_tally_data["energy_bins"][i],
                                "energy_bin_max": active_tally_data["energy_bins"][i+1],
                                "value": val, "relative_error": err
                            })
                        else: # Should not happen if data is consistent
                            print(f"Warning (Tally {active_tally_data['number']}): Mismatch between result pairs and energy bins. Result pair {i} has no upper energy bound.")
                    else: # Total line for binned tallies
                        all_tally_results_list.append({
                            "tally_number": active_tally_data["number"], "energy_bin_idx": -1,
                            "energy_bin_min": active_tally_data["energy_bins"][0] if active_tally_data["energy_bins"] else None,
                            "energy_bin_max": active_tally_data["energy_bins"][-1] if active_tally_data["energy_bins"] else None,
                            "value": val, "relative_error": err
                        })
            # print(f"DEBUG: Flushed tally {active_tally_data['number']}. all_tally_results_list now has {len(all_tally_results_list)} items.")
        elif active_tally_data["number"]: # Tally header was found, but no results pairs (e.g. only ET)
             print(f"DEBUG: Tally {active_tally_data['number']} had no VALS data to flush or was incomplete.")
        
        # Reset active_tally_data for the next tally
        active_tally_data = {"number": None, "energy_bins": [], "results_pairs": []}


    try:
        with open(filepath, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line_stripped = line.strip()
                # print(f"DEBUG Line {line_num}: '{line_stripped[:40]}' | Tally: {active_tally_data['number']}, ET: {in_et_section}, VALS: {in_vals_section}")

                if not line_stripped:
                    continue

                if line_stripped.lower().startswith("tally "):
                    if active_tally_data["number"]: # If there was a previous tally, flush it
                        flush_active_tally_to_list()
                    
                    parts = line_stripped.split()
                    if len(parts) > 1:
                        active_tally_data["number"] = parts[1]
                        # print(f"DEBUG: New Tally Started: {active_tally_data['number']}")
                        in_et_section = False
                        in_vals_section = False
                    else:
                        raise ValueError(f"Line {line_num}: Malformed tally header: {line_stripped}")
                    continue # Process next line

                # --- Process sections only if we are inside a defined tally ---
                if active_tally_data["number"] is None:
                    continue
                
                if line_stripped.lower().startswith("et "):
                    in_et_section = True
                    in_vals_section = False
                    continue 
                
                if in_et_section:
                    if line_stripped.lower().startswith("vals") or line_stripped.lower().startswith("tfc"):
                        in_et_section = False
                        # If it's "vals", the next block will handle it. If "tfc", vals is skipped/done for this tally.
                    else:
                        try:
                            numbers = [float(n) for n in float_regex.findall(line_stripped)]
                            active_tally_data["energy_bins"].extend(numbers)
                        except ValueError as ve:
                            raise ValueError(f"Line {line_num} (Tally {active_tally_data['number']}, ET): Convert error: {ve} in '{line_stripped}'")
                        continue # Important to continue after processing an ET line

                # This condition must be re-evaluated if in_et_section was just turned off by "vals"
                if line_stripped.lower().startswith("vals"):
                    in_vals_section = True
                    in_et_section = False # Explicitly turn off ET if VALS starts
                    continue

                if in_vals_section:
                    if line_stripped.lower().startswith("tfc"):
                        in_vals_section = False # VALS section ends here
                        # Data will be flushed when next "tally" or EOF is hit
                    else: 
                        # <<< MODIFICATION START >>>
                        if line_stripped.startswith("#"):
                            # print(f"DEBUG: Skipping comment line in VALS: {line_stripped}") # Optional debug
                            pass # Effectively skips to the main continue at the end of in_vals_section
                        # <<< MODIFICATION END >>>
                        else: # Only try to parse numbers if it's not a comment
                            try:
                                numbers = [float(n) for n in float_regex.findall(line_stripped)]
                            except ValueError as ve:
                                 raise ValueError(f"Line {line_num} (Tally {active_tally_data['number']}, VALS): Convert error: {ve} in '{line_stripped}'")

                            if len(numbers) % 2 == 0:
                                for i in range(0, len(numbers), 2):
                                    active_tally_data["results_pairs"].append([numbers[i], numbers[i+1]])
                            elif numbers: # Odd number of items on a line
                                print(f"Warning line {line_num} for tally {active_tally_data['number']}: Non-pair numbers in vals line: {line_stripped}.")
                                if len(numbers) == 1:
                                    active_tally_data["results_pairs"].append([numbers[0], 0.0]) # Assume error is 0.0
                                    print(f"  -> Stored as [{numbers[0]}, 0.0]")
                    # Continue to process next line, whether it's another vals line or tfc,
                    # or if it was a comment line that got skipped by the new logic.
                    continue
            
            # After the loop, flush any remaining active tally data
            if active_tally_data["number"]:
                flush_active_tally_to_list()

        if not all_tally_results_list:
            print(f"Warning: No tally data successfully parsed and stored. Last active tally (if any): {active_tally_data.get('number', 'None')}")
            return pd.DataFrame()
            
        return pd.DataFrame(all_tally_results_list)

    except FileNotFoundError:
        raise FileNotFoundError(f"Error: File not found at {filepath}")
    except Exception as e:
        current_tally_for_error = active_tally_data.get('number', 'UNKNOWN')
        raise Exception(f"An error occurred: {e} (Processing Tally: {current_tally_for_error}, Line approx: {line_num if 'line_num' in locals() else 'N/A'})")

# --- Example Usage (Same as before) ---
if __name__ == "__main__":
    dummy_file_content_multi = """
mcnp   6    06/02/25 19:00:00    1        100000      12345
Problem Title: Test_Multi_Tally

tally   115               -1   1   0
 et      4
   0.0E+00  1.0E-03  2.0E-03  3.0E-03
 vals
   1.0E-05 0.10  2.0E-05 0.05
   3.0E-05 0.02
   # Total for Tally 115
   6.0E-05 0.01 
 tfc     blah

tally   125               -1   1   0
 description for 125
 et      3
   0.0E+00  0.5E-03  1.0E-03
 vals
   5.0E-06 0.20
   7.0E-06 0.15
   # Total for Tally 125
   1.2E-05 0.03
 tfc     blah blah

tally   31  # An F1 type tally (often no energy bins, just total)
 vals
   1.234E-02 0.0050
 tfc blah

tally 41 # Another F1 type, but let's give it energy bins this time for testing structure
 et 2
  1.0e-2 2.0e-2
 vals
  9.0e-3 0.11
  # No explicit total line, just one bin value
 tfc end of 41

tally 50 # Tally with no vals, only et
 et 3
  1.0 2.0 3.0
 tfc something
    """
    dummy_filepath_multi = "dummy_mcnp_output_multi.txt"
    with open(dummy_filepath_multi, "w") as f:
        f.write(dummy_file_content_multi)

    print(f"Attempting to parse: {dummy_filepath_multi}")
    try:
        df_results = parse_mcnp_tallies_to_df(dummy_filepath_multi)
        if not df_results.empty:
            print("\n--- Parsed Data as Pandas DataFrame ---")
            print(df_results.to_string())
        else:
            print("No data parsed into DataFrame or DataFrame is empty.")
    except Exception as e:
        print(f"Error during parsing example: {e}")

    dummy_file_content_minimal = """
mcnp   6    06/02/25 19:00:00    1        100000      12345
Problem Title: Test_Minimal_Tally
tally   999
# No et or vals, or incomplete
    """
    dummy_filepath_minimal = "dummy_mcnp_output_minimal.txt"
    with open(dummy_filepath_minimal, "w") as f:
        f.write(dummy_file_content_minimal)
    print(f"\nAttempting to parse minimal/incomplete file: {dummy_filepath_minimal}")
    try:
        df_results_minimal = parse_mcnp_tallies_to_df(dummy_filepath_minimal)
        if not df_results_minimal.empty:
            print("\n--- Parsed Data from minimal file ---")
            print(df_results_minimal.to_string())
        else:
            print("No data parsed from minimal file into DataFrame or DataFrame is empty (as expected).")
    except Exception as e:
        print(f"Error during parsing minimal example: {e}")