import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

/**
 * Compiles every regex rule of the dictionaries with the REAL java.util.regex
 * and runs sample lines through them.
 *
 * <p>Why Java and not Python: the mod runs Java patterns, and the two engines
 * disagree exactly where it hurts. A pattern with a wrong number of backslashes
 * in "\\uE000" is valid in one and dead in the other, and the failure is silent
 * - the rule simply never matches. That cost a whole debugging round once.
 *
 * <p>Driven by tools/check_rules.py, which extracts the rules and feeds them
 * here as a tab separated file: pack, pattern, replacement.
 */
public final class RuleCheck {

	private RuleCheck() {
	}

	public static void main(String[] args) throws Exception {
		List<String> lines = Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8);
		List<Pattern> patterns = new ArrayList<>();
		List<String> replacements = new ArrayList<>();
		List<String> packs = new ArrayList<>();
		int broken = 0;

		for (String line : lines) {
			String[] parts = line.split("\t", -1);
			if (parts.length < 3) {
				continue;
			}
			try {
				patterns.add(Pattern.compile(parts[1]));
				replacements.add(parts[2]);
				packs.add(parts[0]);
			} catch (PatternSyntaxException exception) {
				broken++;
				System.out.println("BROKEN\t" + parts[0] + "\t" + parts[1] + "\t" + exception.getDescription());
			}
		}
		System.out.println("COMPILED\t" + patterns.size() + "\t" + broken);

		// Дальше - строки для примерки, по одной на аргумент
		for (int i = 1; i < args.length; i++) {
			String source = args[i];
			String hit = null;
			for (int k = 0; k < patterns.size(); k++) {
				Matcher matcher = patterns.get(k).matcher(source);
				if (matcher.matches()) {
					hit = packs.get(k) + "\t" + matcher.replaceAll(replacements.get(k));
					break;
				}
			}
			System.out.println(hit == null ? "MISS\t" + source : "HIT\t" + source + "\t" + hit);
		}
	}
}
