using System.Security.Cryptography;
using System.Text;

namespace Daf.Core;

/// <summary>
/// The device token the notification area, Save a Link and the alerts use
/// (<c>Authorization: Bearer</c>), never the window's cookie. Kept encrypted for this
/// Windows user alone (DPAPI), the way the Mac keeps it in the Keychain. The self-test
/// keeps its token in memory and never writes one.
/// </summary>
public sealed class TokenStore(string? file)
{
    static readonly byte[] Entropy = Encoding.UTF8.GetBytes("Daf device token");
    string? memory;
    bool read;

    public string? Value
    {
        get
        {
            if (file == null || read) return memory;
            read = true;
            try
            {
                if (File.Exists(file))
                    memory = Encoding.UTF8.GetString(ProtectedData.Unprotect(File.ReadAllBytes(file), Entropy, DataProtectionScope.CurrentUser));
            }
            catch (Exception) { memory = null; }      // another user's, or damaged: as if there were none
            return memory;
        }
    }

    /// <summary>Keeps a new token, or forgets it with null or "". False if Windows wouldn't keep it.</summary>
    public bool Set(string? token)
    {
        var t = token?.Trim() ?? "";
        read = true;
        memory = t.Length == 0 ? null : t;
        if (file == null) return true;
        try
        {
            if (memory == null) { File.Delete(file); return true; }
            CopyStore.Write(file, ProtectedData.Protect(Encoding.UTF8.GetBytes(memory), Entropy, DataProtectionScope.CurrentUser));
            return true;
        }
        catch (Exception)
        {
            memory = null;
            return false;
        }
    }
}
