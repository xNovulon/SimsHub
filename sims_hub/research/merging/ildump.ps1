# Minimal read-only IL dumper for a .NET assembly (no execution of the assembly).
# usage: pwsh ildump.ps1 <dll> <type-regex> [method-regex]
param([string]$Dll, [string]$TypeRx, [string]$MethodRx = '.')
$src = @'
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Text;
using System.Text.RegularExpressions;
using System.Collections.Immutable;

public class SigProv : ISignatureTypeProvider<string, object> {
    MetadataReader md; public SigProv(MetadataReader m){md=m;}
    public string GetPrimitiveType(PrimitiveTypeCode c){return c.ToString();}
    public string GetTypeFromDefinition(MetadataReader r, TypeDefinitionHandle h, byte k){var t=r.GetTypeDefinition(h);return r.GetString(t.Name);}
    public string GetTypeFromReference(MetadataReader r, TypeReferenceHandle h, byte k){var t=r.GetTypeReference(h);return r.GetString(t.Name);}
    public string GetTypeFromSpecification(MetadataReader r, object g, TypeSpecificationHandle h, byte k){return r.GetTypeSpecification(h).DecodeSignature(this,g);}
    public string GetSZArrayType(string e){return e+"[]";}
    public string GetArrayType(string e, ArrayShape s){return e+"[,]";}
    public string GetByReferenceType(string e){return e+"&";}
    public string GetPointerType(string e){return e+"*";}
    public string GetGenericInstantiation(string g, ImmutableArray<string> a){return g+"<"+string.Join(",",a)+">";}
    public string GetGenericTypeParameter(object g,int i){return "!"+i;}
    public string GetGenericMethodParameter(object g,int i){return "!!"+i;}
    public string GetFunctionPointerType(MethodSignature<string> s){return "fnptr";}
    public string GetModifiedType(string m,string u,bool r){return u;}
    public string GetPinnedType(string e){return e;}
}

public static class IlDump {
    static Dictionary<short, OpCode> ops = new Dictionary<short, OpCode>();
    static IlDump(){
        foreach (var f in typeof(OpCodes).GetFields(BindingFlags.Public|BindingFlags.Static)) {
            var o=(OpCode)f.GetValue(null); ops[o.Value]=o; }
    }
    static string TypeName(MetadataReader md, EntityHandle h, SigProv sp){
        switch(h.Kind){
            case HandleKind.TypeDefinition: {var t=md.GetTypeDefinition((TypeDefinitionHandle)h); return md.GetString(t.Namespace)+"."+md.GetString(t.Name);}
            case HandleKind.TypeReference: {var t=md.GetTypeReference((TypeReferenceHandle)h); return md.GetString(t.Namespace)+"."+md.GetString(t.Name);}
            case HandleKind.TypeSpecification: return md.GetTypeSpecification((TypeSpecificationHandle)h).DecodeSignature(sp,null);
        }
        return h.Kind.ToString();
    }
    static string Tok(MetadataReader md, int token, SigProv sp){
        try{
        var h=MetadataTokens.EntityHandle(token);
        switch(h.Kind){
            case HandleKind.MethodDefinition:{var m=md.GetMethodDefinition((MethodDefinitionHandle)h);return TypeName(md,m.GetDeclaringType(),sp)+"::"+md.GetString(m.Name);}
            case HandleKind.MemberReference:{var m=md.GetMemberReference((MemberReferenceHandle)h);return TypeName(md,m.Parent,sp)+"::"+md.GetString(m.Name);}
            case HandleKind.FieldDefinition:{var f=md.GetFieldDefinition((FieldDefinitionHandle)h);return TypeName(md,f.GetDeclaringType(),sp)+"::"+md.GetString(f.Name);}
            case HandleKind.MethodSpecification:{var s=md.GetMethodSpecification((MethodSpecificationHandle)h);return Tok(md,MetadataTokens.GetToken(s.Method),sp)+"<>";}
            default: return TypeName(md,h,sp);
        }}catch(Exception){return "tok"+token.ToString("X8");}
    }
    public static string Run(string dll, string typeRx, string methRx){
        var sb=new StringBuilder();
        using(var fs=System.IO.File.OpenRead(dll)){
        var pe=new PEReader(fs); var md=pe.GetMetadataReader(); var sp=new SigProv(md);
        var trx=new Regex(typeRx); var mrx=new Regex(methRx);
        foreach(var th in md.TypeDefinitions){
            var t=md.GetTypeDefinition(th);
            string full=md.GetString(t.Namespace)+"."+md.GetString(t.Name);
            if(!t.GetDeclaringType().IsNil){var d=md.GetTypeDefinition(t.GetDeclaringType()); full=md.GetString(d.Namespace)+"."+md.GetString(d.Name)+"/"+md.GetString(t.Name);}
            if(!trx.IsMatch(full)) continue;
            sb.AppendLine("TYPE "+full);
            foreach(var fh in t.GetFields()){var f=md.GetFieldDefinition(fh); sb.AppendLine("  field "+f.DecodeSignature(sp,null)+" "+md.GetString(f.Name)+" ["+f.Attributes+"]");}
            foreach(var mh in t.GetMethods()){
                var m=md.GetMethodDefinition(mh); string mn=md.GetString(m.Name);
                if(!mrx.IsMatch(mn)) continue;
                string sig; try{var s=m.DecodeSignature(sp,null); sig=s.ReturnType+" "+mn+"("+string.Join(",",s.ParameterTypes)+")";}catch{sig=mn;}
                sb.AppendLine("  method "+sig);
                if(m.RelativeVirtualAddress==0) continue;
                var body=pe.GetMethodBody(m.RelativeVirtualAddress);
                var il=body.GetILBytes(); int p=0;
                while(p<il.Length){
                    int at=p; short v=il[p++]; if(v==0xFE){v=(short)(0xFE00|il[p++]);}
                    OpCode o; if(!ops.TryGetValue(v,out o)){sb.AppendLine("    ?? "+v);break;}
                    string arg="";
                    switch(o.OperandType){
                        case OperandType.InlineNone: break;
                        case OperandType.ShortInlineBrTarget: {sbyte d=(sbyte)il[p++]; arg="IL_"+(p+d).ToString("X4");break;}
                        case OperandType.ShortInlineI: arg=((sbyte)il[p++]).ToString();break;
                        case OperandType.ShortInlineVar: arg=il[p++].ToString();break;
                        case OperandType.InlineBrTarget: {int d=BitConverter.ToInt32(il,p);p+=4;arg="IL_"+(p+d).ToString("X4");break;}
                        case OperandType.InlineI: {int d=BitConverter.ToInt32(il,p);p+=4;arg=d.ToString()+" (0x"+d.ToString("X")+")";break;}
                        case OperandType.InlineI8: {long d=BitConverter.ToInt64(il,p);p+=8;arg="0x"+d.ToString("X");break;}
                        case OperandType.ShortInlineR: arg=BitConverter.ToSingle(il,p).ToString();p+=4;break;
                        case OperandType.InlineR: arg=BitConverter.ToDouble(il,p).ToString();p+=8;break;
                        case OperandType.InlineVar: arg=BitConverter.ToUInt16(il,p).ToString();p+=2;break;
                        case OperandType.InlineString: {int d=BitConverter.ToInt32(il,p);p+=4;arg="\""+md.GetUserString(MetadataTokens.UserStringHandle(d&0xFFFFFF))+"\"";break;}
                        case OperandType.InlineSwitch: {int n=BitConverter.ToInt32(il,p);p+=4;var l=new List<string>();for(int k=0;k<n;k++){l.Add(BitConverter.ToInt32(il,p).ToString());p+=4;}arg="("+string.Join(",",l)+")";break;}
                        default: {int d=BitConverter.ToInt32(il,p);p+=4;arg=Tok(md,d,sp);break;}
                    }
                    sb.AppendLine("    IL_"+at.ToString("X4")+" "+o.Name+" "+arg);
                }
            }
        }}
        return sb.ToString();
    }
}
'@
Add-Type -TypeDefinition $src -Language CSharp
[IlDump]::Run($Dll, $TypeRx, $MethodRx)
